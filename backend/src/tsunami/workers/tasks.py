"""Celery task definitions for background simulation work."""

import json
from pathlib import Path

import numpy as np

from tsunami.bathymetry.service import BathymetryService
from tsunami.simulation.boussinesq import BoussinesqConfig, run_boussinesq
from tsunami.simulation.grid import create_grid
from tsunami.simulation.inundation import compute_inundation


def run_detail_zone_sync(
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    grid_resolution_m: float,
    duration_seconds: float,
    results_dir: str,
    boundary_conditions=None,
) -> dict:
    """Run Boussinesq detail simulation for a single focus zone.

    This is the synchronous core — called by the Celery task wrapper
    and directly in tests.
    """
    resolution_km = grid_resolution_m / 1000.0
    grid = create_grid(
        lat_min=lat_min, lat_max=lat_max,
        lon_min=lon_min, lon_max=lon_max,
        resolution_km=resolution_km,
    )

    bathy_service = BathymetryService()
    depth = bathy_service.get_bathymetry(grid, source="procedural")
    grid = grid.with_depth(depth)

    initial_eta = np.zeros(grid.depth.shape)

    config = BoussinesqConfig(
        duration_seconds=duration_seconds,
        output_interval_seconds=max(30.0, duration_seconds / 10),
        cfl=0.3,
    )

    result = run_boussinesq(
        grid, initial_eta, config,
        boundary_conditions=boundary_conditions,
    )

    # Compute inundation
    inundation = compute_inundation(grid, result.max_wave_heights, result.max_velocity)

    # Save results
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    geojson = inundation.inundation_extent_geojson()
    geojson_path = out_dir / "inundation.geojson"
    with open(geojson_path, "w") as f:
        json.dump(geojson, f)

    np.save(str(out_dir / "flood_depth.npy"), inundation.flood_depth)

    return {
        "status": "complete",
        "max_runup_m": inundation.max_runup_m,
        "inundation_geojson": geojson,
        "inundation_geojson_path": str(geojson_path),
    }
