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

# Cached low-res global land mask (computed once on first use)
_land_mask_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}


def _get_land_mask(resolution_km: float) -> tuple[np.ndarray, np.ndarray]:
    """Get or compute a cached low-res global land mask.

    Returns (depth, land_mask) arrays at the requested resolution.
    Uses a precomputed cache file to avoid reading the full 7GB GEBCO on every request.
    """
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

    # Build the mask — try GEBCO, fall back to simple latitude-based mask
    grid = create_grid(lat_min=-80, lat_max=80, lon_min=-180, lon_max=180, resolution_km=resolution_km)

    try:
        from tsunami.bathymetry.service import BathymetryService
        svc = BathymetryService(cache_dir=str(cache_dir))
        depth = svc.get_bathymetry(grid, source="gebco")
        depth = np.nan_to_num(depth, nan=0.0, posinf=0.0, neginf=0.0)
    except Exception:
        # Simple fallback: assume everything is ocean (no land masking)
        depth = np.ones(grid.depth.shape) * 4000.0

    mask = depth <= 0

    # Cache to disk for next startup
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

    # Get land mask (cached — fast after first call)
    depth, land_mask = await asyncio.to_thread(_get_land_mask, body.resolution_km)

    # Resize mask if grid shape differs from cached mask
    if depth.shape != grid.depth.shape:
        # Fallback: no masking
        land_mask = np.zeros(grid.depth.shape, dtype=bool)
        depth = np.ones(grid.depth.shape) * 4000.0

    # Generate tide frames
    tide_frames = await asyncio.to_thread(
        generate_tide_frames,
        grid.lat, grid.lon, body.start_datetime,
        body.duration_hours, body.num_frames,
    )

    # Mask land cells
    for _, eta in tide_frames:
        eta[land_mask] = 0.0

    # Downsample if grid is large
    target = 80
    ny, nx = tide_frames[0][1].shape
    sy = max(1, ny // target)
    sx = max(1, nx // target)
    ds_lat = grid.lat[::sy]
    ds_lon = grid.lon[::sx]

    def downsample(arr: np.ndarray) -> np.ndarray:
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

    # Use actual downsampled grid bounds (not original) to avoid shift
    payload = {
        "grid_bounds": {
            "lat_min": float(ds_lat[0]),
            "lat_max": float(ds_lat[-1]),
            "lon_min": float(ds_lon[0]),
            "lon_max": float(ds_lon[-1]),
        },
        "frame_rows": frame_rows,
        "frame_cols": frame_cols,
        "depth_base64": base64.b64encode(depth_ds.astype(np.float32).tobytes()).decode("ascii"),
        "frames": frame_data,
    }

    return JSONResponse(content=payload)
