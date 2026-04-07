"""Tidal animation endpoint."""

import base64
from datetime import datetime

import numpy as np
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from tsunami.bathymetry.service import BathymetryService
from tsunami.config import get_settings
from tsunami.simulation.grid import create_grid
from tsunami.simulation.tides import generate_tide_frames

router = APIRouter(tags=["tides"])


class TideComputeRequest(BaseModel):
    start_datetime: datetime
    duration_hours: float = Field(gt=0, le=48, default=25.0)
    num_frames: int = Field(gt=0, le=200, default=50)
    resolution_km: float = Field(gt=0, default=100.0)


@router.post("/tides/compute")
async def compute_tides(body: TideComputeRequest):
    """Generate global tidal animation frames."""
    grid = create_grid(
        lat_min=-80.0, lat_max=80.0,
        lon_min=-180.0, lon_max=180.0,
        resolution_km=body.resolution_km,
    )

    # Get bathymetry for land masking
    bathy_service = BathymetryService(cache_dir=get_settings().bathymetry_cache_dir)
    try:
        depth = bathy_service.get_bathymetry(grid, source="auto")
        depth = np.nan_to_num(depth, nan=0.0, posinf=0.0, neginf=0.0)
    except Exception:
        depth = np.ones(grid.depth.shape) * 4000.0  # fallback: all ocean

    # Generate tide frames
    tide_frames = generate_tide_frames(
        grid.lat, grid.lon, body.start_datetime,
        duration_hours=body.duration_hours,
        num_frames=body.num_frames,
    )

    # Mask land cells (set tide to 0 where depth <= 0)
    land_mask = depth <= 0
    for _, eta in tide_frames:
        eta[land_mask] = 0.0

    # Downsample if grid is large
    def downsample(arr, target=80):
        ny, nx = arr.shape
        sy = max(1, ny // target)
        sx = max(1, nx // target)
        return arr[::sy, ::sx]

    sample = downsample(tide_frames[0][1])
    frame_rows, frame_cols = sample.shape
    depth_ds = downsample(depth)

    frame_data = []
    for t, eta in tide_frames:
        eta_ds = downsample(eta).astype(np.float32)
        frame_data.append({
            "time_s": round(t, 1),
            "eta_base64": base64.b64encode(eta_ds.tobytes()).decode("ascii"),
        })

    payload = {
        "grid_bounds": {
            "lat_min": float(grid.lat[0]),
            "lat_max": float(grid.lat[-1]),
            "lon_min": float(grid.lon[0]),
            "lon_max": float(grid.lon[-1]),
        },
        "frame_rows": frame_rows,
        "frame_cols": frame_cols,
        "depth_base64": base64.b64encode(depth_ds.astype(np.float32).tobytes()).decode("ascii"),
        "frames": frame_data,
    }

    return JSONResponse(content=payload)
