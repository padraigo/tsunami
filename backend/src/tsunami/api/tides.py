"""Tidal animation endpoint."""

import asyncio
import base64
from datetime import datetime
from pathlib import Path

import numpy as np
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from tsunami.config import get_settings
from tsunami.simulation.grid import create_grid
from tsunami.simulation.tides import generate_tide_frames

router = APIRouter(tags=["tides"])

_land_mask_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}


def _get_land_mask(resolution_km: float) -> tuple[np.ndarray, np.ndarray]:
    """Get or compute a cached low-res global land mask."""
    key = f"{resolution_km}"
    if key in _land_mask_cache:
        return _land_mask_cache[key]

    cache_dir = Path(get_settings().bathymetry_cache_dir)
    cache_file = cache_dir / f"land_mask_{int(resolution_km)}km.npz"

    if cache_file.exists():
        data = np.load(str(cache_file))
        depth, mask = data["depth"], data["mask"]
        _land_mask_cache[key] = (depth, mask)
        return depth, mask

    grid = create_grid(lat_min=-80, lat_max=80, lon_min=-180, lon_max=180, resolution_km=resolution_km)
    try:
        from tsunami.bathymetry.service import BathymetryService
        svc = BathymetryService(cache_dir=str(cache_dir))
        depth = svc.get_bathymetry(grid, source="gebco")
        depth = np.nan_to_num(depth, nan=0.0, posinf=0.0, neginf=0.0)
    except Exception:
        depth = np.ones(grid.depth.shape) * 4000.0

    mask = depth <= 0
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(cache_file), depth=depth.astype(np.float32), mask=mask)
    _land_mask_cache[key] = (depth, mask)
    return depth, mask


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

    depth, land_mask = await asyncio.to_thread(_get_land_mask, body.resolution_km)

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

    # Add a wrap column at the right edge (copy of the first column)
    # to eliminate the dateline seam
    def add_wrap_col(arr: np.ndarray) -> np.ndarray:
        return np.column_stack([arr, arr[:, 0]])

    depth_ds = add_wrap_col(depth_ds)
    frame_cols_out = frame_cols + 1

    frame_data = []
    for t, eta in tide_frames:
        eta_ds = add_wrap_col(downsample(eta)).astype(np.float32)
        frame_data.append({
            "time_s": round(t, 1),
            "eta_base64": base64.b64encode(eta_ds.tobytes()).decode("ascii"),
        })

    # Image bounds: -90..90 lat, -180..180 lon
    # The image stretches across this exact rectangle.
    # With the wrap column, the rightmost pixel duplicates the leftmost,
    # so there's no seam at the dateline.
    payload = {
        "grid_bounds": {
            "lat_min": -85.0,
            "lat_max": 85.0,
            "lon_min": -180.0,
            "lon_max": 180.0,
        },
        "frame_rows": frame_rows,
        "frame_cols": frame_cols_out,
        "depth_base64": base64.b64encode(depth_ds.astype(np.float32).tobytes()).decode("ascii"),
        "frames": frame_data,
    }

    return JSONResponse(content=payload)
