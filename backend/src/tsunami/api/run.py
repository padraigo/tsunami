"""Simulation execution endpoints."""

import json
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tsunami.api.deps import get_db
from tsunami.bathymetry.service import BathymetryService
from tsunami.config import get_settings
from tsunami.models import Simulation, SimulationStatus
from tsunami.schemas import CoarseResultRead
from tsunami.simulation.grid import create_grid, domain_for_magnitude
from tsunami.simulation.impact import detect_coastal_impacts, suggest_focus_zones
from tsunami.simulation.okada import magnitude_to_fault_params, compute_displacement
from tsunami.simulation.swe_solver import SWESolverConfig, SWEState, run_swe

router = APIRouter(tags=["run"])


@router.post("/simulations/{uid}/run-coarse")
async def run_coarse(uid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Simulation).where(Simulation.uid == uid))
    sim = result.scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")

    # Update status
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
        depth = bathy_service.get_bathymetry(grid, source="procedural")
        grid = grid.with_depth(depth)

        # 3. Compute displacement
        fault = magnitude_to_fault_params(
            sim.earthquake_lat, sim.earthquake_lon,
            sim.earthquake_magnitude, sim.earthquake_direction,
        )
        displacement = compute_displacement(fault, grid)

        # 4. Run SWE
        config = SWESolverConfig(
            duration_seconds=sim.duration_hours * 3600,
            output_interval_seconds=max(300.0, sim.duration_hours * 3600 / 20),
            cfl=0.4,
        )
        frames: list[tuple[float, SWEState]] = []

        def save_frame(t: float, state: SWEState):
            frames.append((t, SWEState(
                eta=state.eta.copy(), hu=state.hu.copy(), hv=state.hv.copy(),
            )))

        run_swe(grid, displacement, config, frame_callback=save_frame)

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

        return {
            "status": "coarse_complete",
            "impacts": impacts_data,
            "suggested_zones": zones_data,
            "max_wave_height": float(np.max(max_heights)),
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
