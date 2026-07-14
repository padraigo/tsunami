"""Tidal animation endpoint."""

import asyncio
import base64
from datetime import datetime

import numpy as np
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from tsunami.bathymetry.land_mask import get_land_mask
from tsunami.simulation.grid import create_grid
from tsunami.simulation.tides import generate_tide_frames

router = APIRouter(tags=["tides"])


class TideComputeRequest(BaseModel):
    start_datetime: datetime
    duration_hours: float = Field(gt=0, le=48, default=25.0)
    num_frames: int = Field(gt=0, le=200, default=50)
    resolution_km: float = Field(ge=10.0, le=1000.0, default=100.0)


@router.post("/tides/compute")
async def compute_tides(body: TideComputeRequest):
    """Generate global tidal animation frames."""
    grid = create_grid(
        lat_min=-80.0, lat_max=80.0,
        lon_min=-180.0, lon_max=180.0,
        resolution_km=body.resolution_km,
    )

    depth, land_mask = await asyncio.to_thread(get_land_mask, body.resolution_km)

    if depth.shape != grid.depth.shape:
        land_mask = np.zeros(grid.depth.shape, dtype=bool)
        depth = np.ones(grid.depth.shape) * 4000.0

    tide_frames = await asyncio.to_thread(
        generate_tide_frames,
        grid.lat, grid.lon, body.start_datetime,
        body.duration_hours, body.num_frames,
    )

    for _, eta in tide_frames:
        eta[land_mask] = 0.0

    # Downsample to target size
    target = 80
    ny, nx = tide_frames[0][1].shape
    sy = max(1, ny // target)
    sx = max(1, nx // target)

    def downsample(arr: np.ndarray) -> np.ndarray:
        return arr[::sy, ::sx]

    sample_eta = downsample(tide_frames[0][1])
    depth_ds = downsample(depth)
    frame_rows, frame_cols = sample_eta.shape

    # Add 2 wrap columns: one on each side to overlap past the dateline
    def add_wrap_cols(arr: np.ndarray) -> np.ndarray:
        return np.column_stack([arr[:, -1], arr, arr[:, 0]])

    depth_ds = add_wrap_cols(depth_ds)
    frame_cols_out = frame_cols + 2

    frame_data = []
    for t, eta in tide_frames:
        eta_ds = add_wrap_cols(downsample(eta)).astype(np.float32)
        frame_data.append({
            "time_s": round(t, 1),
            "eta_base64": base64.b64encode(eta_ds.tobytes()).decode("ascii"),
        })

    # Extend lon bounds past -180/180 by one cell so the image overlaps
    # the dateline on both sides, eliminating the seam
    ds_lon = grid.lon[::sx]
    dlon = float(ds_lon[1] - ds_lon[0]) if len(ds_lon) > 1 else 4.0
    payload = {
        "grid_bounds": {
            "lat_min": -85.0,
            "lat_max": 85.0,
            "lon_min": -180.0 - dlon,
            "lon_max": 180.0 + dlon,
        },
        "frame_rows": frame_rows,
        "frame_cols": frame_cols_out,
        "depth_base64": base64.b64encode(depth_ds.astype(np.float32).tobytes()).decode("ascii"),
        "frames": frame_data,
    }

    return JSONResponse(content=payload)
