"""Simulation execution endpoints."""

import asyncio
import base64
import json
import pickle
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tsunami.api.deps import get_db
from tsunami.api.websocket import broadcast
from tsunami.bathymetry.service import BathymetryService
from tsunami.config import get_settings
from tsunami.models import FocusZone, Simulation, SimulationStatus, ZoneSource, ZoneStatus
from tsunami.schemas import CoarseResultRead
from tsunami.simulation.boussinesq import (
    BoussinesqConfig,
    create_boundary_conditions_from_swe,
    run_boussinesq,
)
from tsunami.simulation.grid import Grid, create_grid, domain_for_magnitude
from tsunami.simulation.impact import detect_coastal_impacts, suggest_focus_zones
from tsunami.simulation.inundation import compute_inundation
from tsunami.simulation.okada import magnitude_to_fault_params, compute_displacement
from tsunami.simulation.swe_solver import SWESolverConfig, SWEState, run_swe

router = APIRouter(tags=["run"])


def _downsample(arr: np.ndarray, target: int = 50) -> np.ndarray:
    """Stride-sample a 2D array to approximately target×target."""
    ny, nx = arr.shape
    sy = max(1, ny // target)
    sx = max(1, nx // target)
    return arr[::sy, ::sx]


def _save_frames(frames: list[tuple[float, SWEState]], grid: Grid, results_dir: Path, max_frames: int = 15):
    """Downsample and persist frame snapshots for frontend animation."""
    if not frames:
        return
    step = max(1, len(frames) // max_frames)
    selected = frames[::step]

    grid_bounds = {
        "lat_min": float(grid.lat[0]),
        "lat_max": float(grid.lat[-1]),
        "lon_min": float(grid.lon[0]),
        "lon_max": float(grid.lon[-1]),
    }

    sample = _downsample(selected[0][1].eta)
    frame_rows, frame_cols = sample.shape

    frame_data = []
    for t, state in selected:
        eta = _downsample(state.eta)
        eta = np.where(np.abs(eta) < 0.001, 0.0, eta)
        eta_bytes = eta.astype(np.float32).tobytes()
        frame_data.append({
            "time_s": round(t, 1),
            "eta_base64": base64.b64encode(eta_bytes).decode("ascii"),
        })

    depth_ds = _downsample(grid.depth)
    depth_bytes = depth_ds.astype(np.float32).tobytes()

    payload = {
        "grid_bounds": grid_bounds,
        "frame_rows": frame_rows,
        "frame_cols": frame_cols,
        "depth_base64": base64.b64encode(depth_bytes).decode("ascii"),
        "frames": frame_data,
    }
    with open(results_dir / "frames.json", "w") as f:
        json.dump(payload, f)


def _save_coarse_frames(frames: list[tuple[float, SWEState]], grid: Grid, results_dir: Path):
    """Save full-resolution coarse frames for boundary condition extraction."""
    times = [t for t, _ in frames]
    etas = [state.eta for _, state in frames]
    hus = [state.hu for _, state in frames]
    hvs = [state.hv for _, state in frames]
    np.savez_compressed(
        str(results_dir / "coarse_frames.npz"),
        times=np.array(times),
        etas=np.array(etas),
        hus=np.array(hus),
        hvs=np.array(hvs),
        lat=grid.lat,
        lon=grid.lon,
        depth=grid.depth,
    )


def _load_coarse_frames(results_dir: Path) -> tuple[Grid, list[tuple[float, SWEState]]]:
    """Load saved coarse frames for BC extraction."""
    data = np.load(str(results_dir / "coarse_frames.npz"))
    grid = Grid(lat=data["lat"], lon=data["lon"], depth=data["depth"])
    frames = []
    for i in range(len(data["times"])):
        t = float(data["times"][i])
        state = SWEState(eta=data["etas"][i], hu=data["hus"][i], hv=data["hvs"][i])
        frames.append((t, state))
    return grid, frames


def _run_detail_zone(
    zone_bounds: dict,
    coarse_grid: Grid,
    coarse_frames: list[tuple[float, SWEState]],
    bathy_service: BathymetryService,
    duration_seconds: float,
    resolution_km: float = 5.0,
) -> dict:
    """Run Boussinesq detail simulation for a single focus zone."""
    fine_grid = create_grid(
        lat_min=zone_bounds["lat_min"],
        lat_max=zone_bounds["lat_max"],
        lon_min=zone_bounds["lon_min"],
        lon_max=zone_bounds["lon_max"],
        resolution_km=resolution_km,
    )

    # Get high-res bathymetry for the zone
    depth = bathy_service.get_bathymetry(fine_grid, source="auto")
    depth = np.nan_to_num(depth, nan=0.0, posinf=0.0, neginf=0.0)
    from scipy.ndimage import uniform_filter
    if depth.size > 100:
        depth = uniform_filter(depth, size=3, mode='nearest')
    fine_grid = fine_grid.with_depth(depth)

    # Extract boundary conditions from coarse solution
    bc = create_boundary_conditions_from_swe(coarse_grid, fine_grid, coarse_frames)

    # Initial eta from coarse solution interpolated to fine grid
    initial_eta = np.zeros(fine_grid.depth.shape)

    config = BoussinesqConfig(
        duration_seconds=duration_seconds,
        output_interval_seconds=max(30.0, duration_seconds / 10),
        cfl=0.3,
    )

    result = run_boussinesq(fine_grid, initial_eta, config, boundary_conditions=bc)

    # Compute inundation
    inundation = compute_inundation(fine_grid, result.max_wave_heights, result.max_velocity)

    return {
        "max_runup_m": inundation.max_runup_m,
        "inundation_geojson": inundation.inundation_extent_geojson(),
        "max_wave_height": float(np.nanmax(result.max_wave_heights)) if result.max_wave_heights.size > 0 else 0.0,
    }


@router.post("/simulations/{uid}/run-coarse")
async def run_coarse(uid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Simulation).where(Simulation.uid == uid))
    sim = result.scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")

    sim.status = SimulationStatus.RUNNING_COARSE
    await db.commit()

    try:
        # 1. Create grid
        bounds = domain_for_magnitude(
            sim.earthquake_lat, sim.earthquake_lon, sim.earthquake_magnitude,
        )
        grid = create_grid(
            lat_min=bounds["lat_min"], lat_max=bounds["lat_max"],
            lon_min=bounds["lon_min"], lon_max=bounds["lon_max"],
            resolution_km=sim.grid_resolution_km,
        )

        # 2. Get bathymetry
        bathy_service = BathymetryService(
            cache_dir=get_settings().bathymetry_cache_dir,
        )
        depth = bathy_service.get_bathymetry(grid, source="auto")
        depth = np.nan_to_num(depth, nan=0.0, posinf=0.0, neginf=0.0)
        from scipy.ndimage import uniform_filter
        if depth.size > 100:
            depth = uniform_filter(depth, size=3, mode='nearest')
        grid = grid.with_depth(depth)

        # 3. Compute displacement
        fault = magnitude_to_fault_params(
            sim.earthquake_lat, sim.earthquake_lon,
            sim.earthquake_magnitude, sim.earthquake_direction,
        )
        displacement = compute_displacement(fault, grid)

        # 4. Run SWE with progress broadcasting
        config = SWESolverConfig(
            duration_seconds=sim.duration_hours * 3600,
            output_interval_seconds=max(300.0, sim.duration_hours * 3600 / 20),
            cfl=0.4,
        )
        frames: list[tuple[float, SWEState]] = []
        loop = asyncio.get_event_loop()
        frame_index = 0

        def save_frame(t: float, state: SWEState):
            nonlocal frame_index
            frames.append((t, SWEState(
                eta=state.eta.copy(), hu=state.hu.copy(), hv=state.hv.copy(),
            )))
            percent = min(100.0, t / config.duration_seconds * 100)
            msg = {
                "type": "coarse_progress",
                "percent": round(percent, 1),
                "time_simulated_s": round(t, 1),
                "frame_index": frame_index,
            }
            frame_index += 1
            loop.call_soon_threadsafe(asyncio.ensure_future, broadcast(uid, msg))

        await asyncio.to_thread(run_swe, grid, displacement, config, save_frame)

        # 5. Compute max heights and detect impacts
        max_heights = np.zeros(grid.depth.shape)
        for _, state in frames:
            np.maximum(max_heights, np.abs(state.eta), out=max_heights)

        impacts = detect_coastal_impacts(
            grid, max_heights, depth_threshold=300.0, height_threshold=0.1,
        )
        zones = suggest_focus_zones(impacts, cluster_radius_km=200.0)

        # 6. Save results
        results_dir = Path(get_settings().results_dir) / sim.uid
        results_dir.mkdir(parents=True, exist_ok=True)

        np.save(str(results_dir / "max_heights.npy"), max_heights)
        _save_frames(frames, grid, results_dir)
        _save_coarse_frames(frames, grid, results_dir)

        impacts_data = [
            {"lat": imp.lat, "lon": imp.lon, "max_height": imp.max_height,
             "arrival_time_s": imp.arrival_time_s}
            for imp in impacts
        ]
        zones_data = [
            {"lat_min": z.lat_min, "lat_max": z.lat_max,
             "lon_min": z.lon_min, "lon_max": z.lon_max,
             "max_impact_height": z.max_impact_height,
             "impact_count": z.impact_count}
            for z in zones
        ]

        sim.impacts_json = json.dumps({"impacts": impacts_data, "zones": zones_data})
        sim.coarse_result_path = str(results_dir)
        sim.status = SimulationStatus.COARSE_COMPLETE
        await db.commit()

        await broadcast(uid, {"type": "coarse_complete", "percent": 100})

        # 7. Auto-create focus zones and run detail simulations
        detail_results = []
        # Limit to top 3 zones by impact height to keep run time reasonable
        top_zones = sorted(zones, key=lambda z: z.max_impact_height, reverse=True)[:3]

        if top_zones:
            sim.status = SimulationStatus.RUNNING_DETAIL
            await db.commit()
            await broadcast(uid, {"type": "detail_starting", "zone_count": len(top_zones)})

        for i, z in enumerate(top_zones):
            zone_record = FocusZone(
                simulation_id=sim.id,
                name=f"Auto Zone {i + 1}",
                lat_min=z.lat_min,
                lat_max=z.lat_max,
                lon_min=z.lon_min,
                lon_max=z.lon_max,
                source=ZoneSource.AUTO,
                grid_resolution_m=5000.0,  # 5km detail resolution
                status=ZoneStatus.RUNNING,
            )
            db.add(zone_record)
            await db.commit()
            await db.refresh(zone_record)

            await broadcast(uid, {
                "type": "detail_progress",
                "zone_uid": zone_record.uid,
                "zone_name": zone_record.name,
                "zone_index": i,
                "zone_count": len(top_zones),
                "percent": 0,
            })

            try:
                zone_bounds = {
                    "lat_min": z.lat_min, "lat_max": z.lat_max,
                    "lon_min": z.lon_min, "lon_max": z.lon_max,
                }
                detail = await asyncio.to_thread(
                    _run_detail_zone,
                    zone_bounds, grid, frames, bathy_service,
                    duration_seconds=min(config.duration_seconds, 1800.0),  # cap at 30min
                    resolution_km=5.0,
                )

                # Save detail results
                zone_dir = results_dir / f"zone_{zone_record.uid}"
                zone_dir.mkdir(parents=True, exist_ok=True)
                with open(zone_dir / "inundation.geojson", "w") as f:
                    json.dump(detail["inundation_geojson"], f)

                zone_record.status = ZoneStatus.COMPLETE
                zone_record.max_runup_m = detail["max_runup_m"]
                zone_record.inundation_geojson_path = str(zone_dir / "inundation.geojson")
                await db.commit()

                detail_results.append({
                    "zone_uid": zone_record.uid,
                    "zone_name": zone_record.name,
                    "max_runup_m": detail["max_runup_m"],
                    "max_wave_height": detail["max_wave_height"],
                })

                await broadcast(uid, {
                    "type": "detail_progress",
                    "zone_uid": zone_record.uid,
                    "zone_name": zone_record.name,
                    "zone_index": i,
                    "zone_count": len(top_zones),
                    "percent": 100,
                })

            except Exception as e:
                zone_record.status = ZoneStatus.FAILED
                zone_record.error_message = str(e)
                await db.commit()

        # Update final status
        sim.status = SimulationStatus.COMPLETE if top_zones else SimulationStatus.COARSE_COMPLETE
        await db.commit()
        await broadcast(uid, {"type": "complete"})

        max_wh = float(np.nanmax(max_heights)) if max_heights.size > 0 else 0.0
        if not np.isfinite(max_wh):
            max_wh = 0.0

        return {
            "status": sim.status.value,
            "impacts": impacts_data,
            "suggested_zones": zones_data,
            "max_wave_height": max_wh,
            "detail_zones": detail_results,
        }

    except Exception as e:
        sim.status = SimulationStatus.FAILED
        sim.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/simulations/{uid}/coarse-result", response_model=CoarseResultRead)
async def get_coarse_result(uid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Simulation).where(Simulation.uid == uid))
    sim = result.scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")

    impacts_data = json.loads(sim.impacts_json) if sim.impacts_json else {"impacts": [], "zones": []}

    max_wave_height = None
    if sim.coarse_result_path:
        heights_path = Path(sim.coarse_result_path) / "max_heights.npy"
        if heights_path.exists():
            max_heights = np.load(str(heights_path))
            max_wave_height = float(np.max(max_heights))

    return CoarseResultRead(
        status=sim.status.value,
        impacts=impacts_data.get("impacts", []),
        suggested_zones=impacts_data.get("zones", []),
        max_wave_height=max_wave_height,
    )


@router.get("/simulations/{uid}/detail-results")
async def get_detail_results(uid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Simulation).options(selectinload(Simulation.focus_zones)).where(Simulation.uid == uid)
    )
    sim = result.scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")

    zone_results = []
    for zone in sim.focus_zones:
        zone_data = {
            "zone_uid": zone.uid,
            "zone_name": zone.name,
            "status": zone.status.value,
            "max_runup_m": zone.max_runup_m,
            "bounds": {
                "lat_min": zone.lat_min, "lat_max": zone.lat_max,
                "lon_min": zone.lon_min, "lon_max": zone.lon_max,
            },
            "inundation_geojson": None,
        }
        if zone.inundation_geojson_path:
            geojson_path = Path(zone.inundation_geojson_path)
            if geojson_path.exists():
                with open(geojson_path) as f:
                    zone_data["inundation_geojson"] = json.load(f)
        zone_results.append(zone_data)

    return {"zones": zone_results}
