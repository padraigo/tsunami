"""MCP server for the tsunami simulator.

Provides tools, resources, and prompts for AI assistants to interact
with the tsunami simulation engine via the Model Context Protocol.
"""

import json
from pathlib import Path

import numpy as np
from mcp.server.fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from tsunami.api.deps import _get_session_factory
from tsunami.config import get_settings
from tsunami.models import FocusZone, Simulation, ZoneSource

mcp = FastMCP(
    "Tsunami Simulator",
    instructions=(
        "Tsunami simulation engine for modeling earthquake-generated tsunamis. "
        "Typical workflow: list_presets or create_simulation -> run_coarse -> get_results -> get_detail_results. "
        "Simulations run physics solvers (SWE + Boussinesq) and can take minutes at fine resolution. "
        "Use grid_resolution_km=20-50 for fast runs, 2-5 for production quality."
    ),
)


async def _get_db():
    factory = _get_session_factory()
    async with factory() as session:
        yield session


async def _get_session():
    factory = _get_session_factory()
    return factory()


# --- TOOLS ---------------------------------------------------------------


@mcp.tool()
async def tsunami_health() -> str:
    """Check if the tsunami simulator backend is running and database is accessible."""
    try:
        session = await _get_session()
        async with session:
            result = await session.execute(select(Simulation).limit(1))
            count_result = await session.execute(select(Simulation))
            sims = count_result.scalars().all()
        return json.dumps({"status": "ok", "simulation_count": len(sims)})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
async def tsunami_list_simulations() -> str:
    """List all tsunami simulations with their status, earthquake parameters, and creation time.

    Returns simulations ordered by creation time (newest first).
    """
    session = await _get_session()
    async with session:
        result = await session.execute(
            select(Simulation).order_by(Simulation.created_at.desc())
        )
        sims = result.scalars().all()
        data = []
        for s in sims:
            data.append({
                "uid": s.uid,
                "name": s.name,
                "status": s.status.value,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "earthquake_lat": s.earthquake_lat,
                "earthquake_lon": s.earthquake_lon,
                "earthquake_magnitude": s.earthquake_magnitude,
                "earthquake_direction": s.earthquake_direction,
            })
        return json.dumps(data, indent=2)


@mcp.tool()
async def tsunami_get_simulation(uid: str) -> str:
    """Get full details for a specific simulation including focus zones.

    Args:
        uid: Simulation UID (UUID format)
    """
    session = await _get_session()
    async with session:
        result = await session.execute(
            select(Simulation).options(selectinload(Simulation.focus_zones)).where(Simulation.uid == uid)
        )
        sim = result.scalar_one_or_none()
        if not sim:
            return json.dumps({"error": f"Simulation {uid} not found"})

        zones = [{
            "uid": z.uid, "name": z.name, "status": z.status.value,
            "source": z.source.value, "max_runup_m": z.max_runup_m,
            "lat_min": z.lat_min, "lat_max": z.lat_max,
            "lon_min": z.lon_min, "lon_max": z.lon_max,
        } for z in sim.focus_zones]

        return json.dumps({
            "uid": sim.uid, "name": sim.name, "status": sim.status.value,
            "created_at": sim.created_at.isoformat() if sim.created_at else None,
            "earthquake_lat": sim.earthquake_lat, "earthquake_lon": sim.earthquake_lon,
            "earthquake_magnitude": sim.earthquake_magnitude,
            "earthquake_direction": sim.earthquake_direction,
            "earthquake_depth_km": sim.earthquake_depth_km,
            "earthquake_datetime": sim.earthquake_datetime.isoformat() if sim.earthquake_datetime else None,
            "grid_resolution_km": sim.grid_resolution_km,
            "duration_hours": sim.duration_hours,
            "focus_zones": zones,
            "error_message": sim.error_message,
        }, indent=2)


@mcp.tool()
async def tsunami_create_simulation(
    name: str,
    earthquake_lat: float,
    earthquake_lon: float,
    earthquake_magnitude: float,
    earthquake_direction: float = 0.0,
    earthquake_depth_km: float = 15.0,
    grid_resolution_km: float = 2.0,
    duration_hours: float = 6.0,
    earthquake_datetime: str | None = None,
) -> str:
    """Create a new tsunami simulation scenario. After creating, use tsunami_run_coarse to execute it.

    Args:
        name: Descriptive name for the simulation scenario
        earthquake_lat: Epicenter latitude (-90 to 90)
        earthquake_lon: Epicenter longitude (-180 to 180)
        earthquake_magnitude: Richter magnitude (5.0 to 10.0). Higher = larger tsunami
        earthquake_direction: Fault strike direction in degrees (0-359). Controls which direction the tsunami propagates
        earthquake_depth_km: Hypocenter depth in km (default 15). Shallower = stronger surface displacement
        grid_resolution_km: Coarse grid cell size in km. Use 20-50 for fast runs, 2-5 for quality
        duration_hours: How long to simulate (max 48h). 6h covers most Pacific basin crossings
        earthquake_datetime: Optional UTC datetime (ISO 8601) for tidal phase coupling
    """
    from datetime import datetime as dt

    session = await _get_session()
    async with session:
        sim = Simulation(
            name=name,
            earthquake_lat=earthquake_lat,
            earthquake_lon=earthquake_lon,
            earthquake_magnitude=earthquake_magnitude,
            earthquake_direction=earthquake_direction,
            earthquake_depth_km=earthquake_depth_km,
            grid_resolution_km=grid_resolution_km,
            duration_hours=duration_hours,
        )
        if earthquake_datetime:
            sim.earthquake_datetime = dt.fromisoformat(earthquake_datetime)
        session.add(sim)
        await session.commit()
        await session.refresh(sim)
        return json.dumps({
            "uid": sim.uid, "name": sim.name, "status": sim.status.value,
            "message": f"Simulation created. Run it with tsunami_run_coarse(uid='{sim.uid}')",
        }, indent=2)


@mcp.tool()
async def tsunami_run_coarse(uid: str) -> str:
    """Execute the coarse SWE simulation for a pending simulation.

    This runs the full simulation pipeline:
    1. Computes earthquake displacement (Okada fault model)
    2. Runs Shallow Water Equations solver across the ocean basin
    3. Detects coastal impact zones automatically
    4. Runs Boussinesq detail simulations for top 3 impact zones

    Runtime depends on grid_resolution_km: ~30s at 20km, 5-10min at 2km.

    Args:
        uid: Simulation UID to execute
    """
    import httpx
    # Delegate to the REST endpoint which handles the full pipeline
    # (SWE solver, impact detection, detail zones, WebSocket broadcasting)
    backend_url = get_settings().internal_api_url
    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
        resp = await client.post(f"{backend_url}/api/simulations/{uid}/run-coarse")
        if resp.status_code != 200:
            return json.dumps({"error": f"Run failed: {resp.text}"})
        return resp.text


@mcp.tool()
async def tsunami_get_results(uid: str) -> str:
    """Get coarse simulation results: coastal impacts, suggested zones, and max wave height.

    Call this after tsunami_run_coarse completes. Returns impact points with
    lat/lon, wave height, and arrival time, plus auto-detected focus zones.

    Args:
        uid: Simulation UID
    """
    session = await _get_session()
    async with session:
        result = await session.execute(select(Simulation).where(Simulation.uid == uid))
        sim = result.scalar_one_or_none()
        if not sim:
            return json.dumps({"error": f"Simulation {uid} not found"})

        impacts_data = json.loads(sim.impacts_json) if sim.impacts_json else {"impacts": [], "zones": []}

        max_wave_height = None
        if sim.coarse_result_path:
            heights_path = Path(sim.coarse_result_path) / "max_heights.npy"
            if heights_path.exists():
                max_heights = np.load(str(heights_path))
                val = float(np.nanmax(max_heights))
                max_wave_height = val if np.isfinite(val) else None

        return json.dumps({
            "status": sim.status.value,
            "impacts": impacts_data.get("impacts", []),
            "suggested_zones": impacts_data.get("zones", []),
            "max_wave_height": max_wave_height,
        }, indent=2)


@mcp.tool()
async def tsunami_get_detail_results(uid: str) -> str:
    """Get high-resolution detail zone results (inundation, runup) from Boussinesq simulations.

    Returns results for each auto-created or user-defined focus zone, including
    max runup height and inundation extent GeoJSON.

    Args:
        uid: Simulation UID
    """
    session = await _get_session()
    async with session:
        result = await session.execute(
            select(Simulation).options(selectinload(Simulation.focus_zones)).where(Simulation.uid == uid)
        )
        sim = result.scalar_one_or_none()
        if not sim:
            return json.dumps({"error": f"Simulation {uid} not found"})

        zones = []
        for zone in sim.focus_zones:
            zone_data = {
                "zone_uid": zone.uid, "zone_name": zone.name,
                "status": zone.status.value, "max_runup_m": zone.max_runup_m,
                "bounds": {"lat_min": zone.lat_min, "lat_max": zone.lat_max,
                           "lon_min": zone.lon_min, "lon_max": zone.lon_max},
                "inundation_geojson": None,
            }
            if zone.inundation_geojson_path:
                geojson_path = Path(zone.inundation_geojson_path)
                if geojson_path.exists():
                    with open(geojson_path) as f:
                        zone_data["inundation_geojson"] = json.load(f)
            zones.append(zone_data)

        return json.dumps({"zones": zones}, indent=2)


@mcp.tool()
async def tsunami_list_presets() -> str:
    """List preset earthquake locations for quick simulation setup.

    Returns famous historical earthquakes with pre-configured parameters.
    """
    presets = [
        {"name": "Tohoku, Japan", "lat": 38.3, "lon": 142.4, "magnitude": 9.1, "direction": 290.0},
        {"name": "Sumatra, Indonesia", "lat": 3.3, "lon": 95.9, "magnitude": 9.1, "direction": 340.0},
        {"name": "Chile (Maule)", "lat": -35.8, "lon": -72.7, "magnitude": 8.8, "direction": 280.0},
        {"name": "Alaska (1964)", "lat": 61.0, "lon": -147.5, "magnitude": 9.2, "direction": 210.0},
        {"name": "Cascadia (scenario)", "lat": 44.5, "lon": -125.0, "magnitude": 9.0, "direction": 260.0},
        {"name": "Lisbon (1755)", "lat": 36.0, "lon": -11.0, "magnitude": 8.7, "direction": 300.0},
    ]
    return json.dumps(presets, indent=2)


@mcp.tool()
async def tsunami_delete_simulation(uid: str) -> str:
    """Delete a simulation and all its results (focus zones, frames, inundation data).

    Args:
        uid: Simulation UID to delete
    """
    session = await _get_session()
    async with session:
        result = await session.execute(
            select(Simulation).options(selectinload(Simulation.focus_zones)).where(Simulation.uid == uid)
        )
        sim = result.scalar_one_or_none()
        if not sim:
            return json.dumps({"error": f"Simulation {uid} not found"})

        # Clean up result files
        if sim.coarse_result_path:
            import shutil
            results_path = Path(sim.coarse_result_path)
            if results_path.exists():
                shutil.rmtree(results_path, ignore_errors=True)

        await session.delete(sim)
        await session.commit()
        return json.dumps({"ok": True, "message": f"Simulation {uid} deleted"})


@mcp.tool()
async def tsunami_list_focus_zones(uid: str) -> str:
    """List focus zones for a simulation (auto-created from impact detection or user-defined).

    Args:
        uid: Simulation UID
    """
    session = await _get_session()
    async with session:
        result = await session.execute(
            select(Simulation).options(selectinload(Simulation.focus_zones)).where(Simulation.uid == uid)
        )
        sim = result.scalar_one_or_none()
        if not sim:
            return json.dumps({"error": f"Simulation {uid} not found"})

        zones = [{
            "uid": z.uid, "name": z.name, "status": z.status.value,
            "source": z.source.value, "max_runup_m": z.max_runup_m,
            "lat_min": z.lat_min, "lat_max": z.lat_max,
            "lon_min": z.lon_min, "lon_max": z.lon_max,
            "grid_resolution_m": z.grid_resolution_m,
        } for z in sim.focus_zones]

        return json.dumps(zones, indent=2)


@mcp.tool()
async def tsunami_create_focus_zone(
    simulation_uid: str,
    name: str,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    grid_resolution_m: float = 100.0,
) -> str:
    """Create a custom focus zone for detailed Boussinesq simulation on a specific coastal area.

    Args:
        simulation_uid: Parent simulation UID
        name: Descriptive name for the zone (e.g. "Tokyo Bay")
        lat_min: Southern boundary latitude
        lat_max: Northern boundary latitude
        lon_min: Western boundary longitude
        lon_max: Eastern boundary longitude
        grid_resolution_m: Detail grid resolution in meters (default 100m)
    """
    session = await _get_session()
    async with session:
        result = await session.execute(select(Simulation).where(Simulation.uid == simulation_uid))
        sim = result.scalar_one_or_none()
        if not sim:
            return json.dumps({"error": f"Simulation {simulation_uid} not found"})

        zone = FocusZone(
            simulation_id=sim.id,
            name=name,
            lat_min=lat_min, lat_max=lat_max,
            lon_min=lon_min, lon_max=lon_max,
            source=ZoneSource.USER,
            grid_resolution_m=grid_resolution_m,
        )
        session.add(zone)
        await session.commit()
        await session.refresh(zone)
        return json.dumps({
            "uid": zone.uid, "name": zone.name, "status": zone.status.value,
        }, indent=2)


@mcp.tool()
async def tsunami_delete_focus_zone(simulation_uid: str, zone_uid: str) -> str:
    """Delete a focus zone from a simulation.

    Args:
        simulation_uid: Parent simulation UID
        zone_uid: Focus zone UID to delete
    """
    session = await _get_session()
    async with session:
        result = await session.execute(
            select(FocusZone).where(FocusZone.uid == zone_uid)
        )
        zone = result.scalar_one_or_none()
        if not zone:
            return json.dumps({"error": f"Focus zone {zone_uid} not found"})
        await session.delete(zone)
        await session.commit()
        return json.dumps({"ok": True, "message": f"Zone {zone_uid} deleted"})


@mcp.tool()
async def tsunami_compute_tides(
    start_datetime: str,
    duration_hours: float = 25.0,
    resolution_km: float = 100.0,
) -> str:
    """Compute global tidal animation. Returns frame count and grid info (not raw frame data).

    View the animation at the frontend (http://localhost:3000).

    Args:
        start_datetime: UTC datetime (ISO 8601 format, e.g. "2026-03-11T05:46:00Z")
        duration_hours: Animation duration in hours (default 25, max 48)
        resolution_km: Grid resolution in km (default 100)
    """
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        resp = await client.post(f"{get_settings().internal_api_url}/api/tides/compute", json={
            "start_datetime": start_datetime,
            "duration_hours": duration_hours,
            "resolution_km": resolution_km,
        })
        if resp.status_code != 200:
            return json.dumps({"error": f"Tides computation failed: {resp.text}"})
        data = resp.json()
        return json.dumps({
            "frame_count": len(data.get("frames", [])),
            "grid_size": f"{data.get('frame_rows', 0)}x{data.get('frame_cols', 0)}",
            "grid_bounds": data.get("grid_bounds"),
            "message": "Tidal frames computed. View animation at http://localhost:3000 (click 'Show Global Tides').",
        }, indent=2)


@mcp.tool()
async def tsunami_check_bathymetry(
    lat_min: float, lat_max: float, lon_min: float, lon_max: float,
) -> str:
    """Check which bathymetry data sources are available for a given region.

    GEBCO provides real ocean depth data (~450m resolution).
    Procedural fallback generates synthetic continental shelf for testing.

    Args:
        lat_min: Southern boundary
        lat_max: Northern boundary
        lon_min: Western boundary
        lon_max: Eastern boundary
    """
    from tsunami.bathymetry.service import BathymetryService
    service = BathymetryService(cache_dir=get_settings().bathymetry_cache_dir)
    result = service.check_availability(lat_min, lat_max, lon_min, lon_max)
    return json.dumps(result, indent=2)


@mcp.tool()
async def tsunami_export(uid: str, format: str = "geojson") -> str:
    """Get export data for simulation results.

    Currently supports GeoJSON format (impacts + inundation zones).

    Args:
        uid: Simulation UID
        format: Export format - "geojson" (default)
    """
    return json.dumps({
        "export_url": f"{get_settings().public_api_url}/api/simulations/{uid}/export?format={format}",
        "message": f"Download results at the URL above ({format} format).",
    })


@mcp.tool()
async def tsunami_get_frames(uid: str) -> str:
    """Get wave animation frame metadata for a completed simulation.

    Returns frame count, grid dimensions, and time range. The actual frame
    data (base64 arrays) is rendered by the frontend at http://localhost:3000.

    Args:
        uid: Simulation UID
    """
    session = await _get_session()
    async with session:
        result = await session.execute(select(Simulation).where(Simulation.uid == uid))
        sim = result.scalar_one_or_none()
        if not sim:
            return json.dumps({"error": f"Simulation {uid} not found"})

        if not sim.coarse_result_path:
            return json.dumps({"error": "No results available. Run the simulation first."})

        frames_path = Path(sim.coarse_result_path) / "frames.json"
        if not frames_path.exists():
            return json.dumps({"error": "Frame data not found."})

        with open(frames_path) as f:
            data = json.load(f)

        frame_times = [fr["time_s"] for fr in data.get("frames", [])]
        return json.dumps({
            "frame_count": len(data.get("frames", [])),
            "grid_size": f"{data.get('frame_rows', 0)}x{data.get('frame_cols', 0)}",
            "grid_bounds": data.get("grid_bounds"),
            "time_range_s": [min(frame_times), max(frame_times)] if frame_times else None,
            "message": "View animation at http://localhost:3000",
        }, indent=2)


# --- RESOURCES -----------------------------------------------------------


@mcp.resource("tsunami://simulations")
async def list_simulations_resource() -> str:
    """Browse all tsunami simulations."""
    session = await _get_session()
    async with session:
        result = await session.execute(
            select(Simulation).order_by(Simulation.created_at.desc())
        )
        sims = result.scalars().all()
        data = [{
            "uid": s.uid, "name": s.name, "status": s.status.value,
            "magnitude": s.earthquake_magnitude,
        } for s in sims]
        return json.dumps(data, indent=2)


@mcp.resource("tsunami://simulation/{uid}")
async def get_simulation_resource(uid: str) -> str:
    """Full simulation detail including parameters and focus zones."""
    return await tsunami_get_simulation(uid)


@mcp.resource("tsunami://simulation/{uid}/impacts")
async def get_impacts_resource(uid: str) -> str:
    """Coastal impact summary for a simulation."""
    return await tsunami_get_results(uid)


@mcp.resource("tsunami://presets")
async def list_presets_resource() -> str:
    """Available earthquake preset locations."""
    return await tsunami_list_presets()


@mcp.resource("tsunami://bathymetry/status")
async def bathymetry_status_resource() -> str:
    """Check bathymetry data source availability (global)."""
    return await tsunami_check_bathymetry(-90, 90, -180, 180)


# --- PROMPTS -------------------------------------------------------------


@mcp.prompt()
def guided_simulation() -> str:
    """Step-by-step workflow for creating and running a tsunami simulation."""
    return """Walk the user through creating and running a tsunami simulation:

1. Ask what earthquake scenario they want to model, or suggest using tsunami_list_presets
2. Create the simulation with tsunami_create_simulation
   - For quick testing: use grid_resolution_km=20-50
   - For production quality: use grid_resolution_km=2-5
3. Run with tsunami_run_coarse (this triggers the full pipeline)
4. Check results with tsunami_get_results
5. Review detail zones with tsunami_get_detail_results
6. Point them to http://localhost:3000 to see the wave animation

Key tips:
- Higher magnitude = larger domain = longer runtime
- Earthquake direction controls which coasts get hit hardest
- The simulation auto-detects impact zones and runs detail sims
"""


@mcp.prompt()
def impact_analysis() -> str:
    """Template for analyzing tsunami simulation results."""
    return """Analyze the results of a tsunami simulation:

1. Get results with tsunami_get_results to see:
   - Max wave height across the domain
   - Coastal impact points (lat/lon, height, arrival time)
   - Suggested focus zones

2. Get detail results with tsunami_get_detail_results to see:
   - Max runup height per zone (how far inland water reaches)
   - Inundation extent (flooded area GeoJSON)

3. Provide analysis covering:
   - Which coasts are most affected and why (earthquake direction, bathymetry)
   - Arrival times (early warning potential)
   - Comparison to historical events if relevant
   - Limitations of the simulation (grid resolution, simplified physics)
"""


@mcp.prompt()
def scenario_comparison() -> str:
    """Template for comparing two or more tsunami scenarios."""
    return """Compare multiple tsunami simulation scenarios:

1. List simulations with tsunami_list_simulations
2. For each scenario, get results with tsunami_get_results
3. Compare:
   - Max wave heights
   - Number and severity of coastal impacts
   - Arrival times at key locations
   - Detail zone runup heights

Present findings in a structured table or summary.
"""


@mcp.prompt()
def emergency_assessment() -> str:
    """Template for rapid emergency response tsunami assessment."""
    return """Rapid tsunami threat assessment workflow:

1. Create simulation with the reported earthquake parameters
   - Use grid_resolution_km=20 for fast initial assessment
   - Set earthquake_datetime for accurate tidal coupling

2. Run and analyze:
   - Which populated coastlines are threatened?
   - Estimated arrival times for early warning
   - Expected wave heights at impact

3. If needed, create custom focus zones for specific cities/ports
   with tsunami_create_focus_zone for higher-resolution analysis

4. Summarize threat level and recommended actions
"""
