"""Bathymetry data endpoints."""

import asyncio
import base64
import io

import numpy as np
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

from tsunami.api.tides import _get_land_mask
from tsunami.bathymetry.service import BathymetryService
from tsunami.config import get_settings
from tsunami.simulation.grid import create_grid

router = APIRouter(tags=["bathymetry"])


def _depth_to_rgba(depth_2d: np.ndarray) -> np.ndarray:
    """Colorize a depth array (positive = ocean, negative = land elevation) to RGBA."""
    rows, cols = depth_2d.shape
    rgba = np.zeros((rows, cols, 4), dtype=np.uint8)

    ocean = depth_2d > 0
    land = ~ocean

    # Ocean: light cyan to dark navy based on depth (0-8000m)
    d = np.clip(depth_2d[ocean], 0, 8000)
    t = d / 8000.0
    rgba[ocean, 0] = (30 * (1 - t)).astype(np.uint8)
    rgba[ocean, 1] = (180 - 140 * t).astype(np.uint8)
    rgba[ocean, 2] = (255 - 100 * t).astype(np.uint8)
    rgba[ocean, 3] = 255

    # Land: green (low) -> brown (mid) -> white (high)
    elev = np.abs(depth_2d[land])
    low = elev < 200
    mid = (elev >= 200) & (elev < 2000)
    high = elev >= 2000

    land_rgba = np.zeros((elev.size, 4), dtype=np.uint8)
    t_low = elev[low] / 200.0
    land_rgba[low, 0] = (80 + 100 * t_low).astype(np.uint8)
    land_rgba[low, 1] = (160 - 40 * t_low).astype(np.uint8)
    land_rgba[low, 2] = (60 - 20 * t_low).astype(np.uint8)
    land_rgba[low, 3] = 255

    t_mid = (elev[mid] - 200) / 1800.0
    land_rgba[mid, 0] = (180 + 50 * t_mid).astype(np.uint8)
    land_rgba[mid, 1] = (120 - 40 * t_mid).astype(np.uint8)
    land_rgba[mid, 2] = (40 + 20 * t_mid).astype(np.uint8)
    land_rgba[mid, 3] = 255

    t_high = np.clip((elev[high] - 2000) / 4000.0, 0, 1)
    land_rgba[high, 0] = (230 + 25 * t_high).astype(np.uint8)
    land_rgba[high, 1] = (80 + 175 * t_high).astype(np.uint8)
    land_rgba[high, 2] = (60 + 195 * t_high).astype(np.uint8)
    land_rgba[high, 3] = 255

    rgba[land] = land_rgba
    return rgba


@router.get("/bathymetry/check")
async def check_bathymetry(
    lat_min: float = Query(...),
    lat_max: float = Query(...),
    lon_min: float = Query(...),
    lon_max: float = Query(...),
):
    service = BathymetryService(cache_dir=get_settings().bathymetry_cache_dir)
    return service.check_availability(lat_min, lat_max, lon_min, lon_max)


@router.get("/bathymetry/global-depth")
async def global_depth(
    resolution_km: float = Query(default=100.0),
):
    """Return a downsampled global depth grid."""
    grid = create_grid(
        lat_min=-80.0, lat_max=80.0,
        lon_min=-180.0, lon_max=180.0,
        resolution_km=resolution_km,
    )

    depth, _land_mask_arr = await asyncio.to_thread(_get_land_mask, resolution_km)

    # Downsample to ~80x80 target
    target = 80
    ny, nx = depth.shape
    sy = max(1, ny // target)
    sx = max(1, nx // target)

    def downsample(arr: np.ndarray) -> np.ndarray:
        return arr[::sy, ::sx]

    depth_ds = downsample(depth)
    frame_rows, frame_cols = depth_ds.shape

    # Add 2 wrap columns for dateline overlap
    def add_wrap_cols(arr: np.ndarray) -> np.ndarray:
        return np.column_stack([arr[:, -1], arr, arr[:, 0]])

    depth_ds = add_wrap_cols(depth_ds)
    frame_cols_out = frame_cols + 2

    # Extend lon bounds past -180/180 by one cell width
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
        "frames": [],
    }

    return JSONResponse(content=payload)


@router.get("/bathymetry/global-depth.png")
async def global_depth_png(
    resolution_km: float = Query(default=100.0),
):
    """Return the global elevation/depth map as a ready-to-use PNG image.

    The image is pre-warped to match MapLibre's Mercator projection so the
    frontend can use it directly as an image source.
    """
    from PIL import Image

    depth, _land_mask_arr = await asyncio.to_thread(_get_land_mask, resolution_km)

    # Downsample to ~160 rows for reasonable PNG size
    target = 160
    ny, nx = depth.shape
    sy = max(1, ny // target)
    sx = max(1, nx // target)

    depth_ds = depth[::sy, ::sx]

    # Wrap longitudinally so the image spans past the dateline
    depth_ds = np.column_stack([depth_ds[:, -1:], depth_ds, depth_ds[:, :1]])

    # Flip rows so index 0 = north (top of image), since data has row 0 = south
    depth_ds = depth_ds[::-1, :]

    # Mercator pre-warp the rows. Source lat range is [-80, 80] (data) and
    # the image will be placed at Mercator bounds [-85, 85] in the frontend.
    src_rows = depth_ds.shape[0]
    src_lat_max = 80.0
    src_lat_min = -80.0

    def merc_y(lat_deg: float) -> float:
        lat_clamped = max(-85.0, min(85.0, lat_deg))
        lat_rad = np.radians(lat_clamped)
        return float(np.log(np.tan(np.pi / 4 + lat_rad / 2)))

    dst_rows = 400
    dst_lat_max = 85.0
    dst_lat_min = -85.0
    merc_max = merc_y(dst_lat_max)
    merc_min = merc_y(dst_lat_min)

    warped = np.zeros((dst_rows, depth_ds.shape[1]), dtype=np.float32)
    for row in range(dst_rows):
        frac = row / (dst_rows - 1)
        merc_val = merc_max - frac * (merc_max - merc_min)
        lat_deg = np.degrees(2 * np.arctan(np.exp(merc_val)) - np.pi / 2)
        if lat_deg > src_lat_max or lat_deg < src_lat_min:
            continue
        src_row_f = ((src_lat_max - lat_deg) / (src_lat_max - src_lat_min)) * (src_rows - 1)
        src_row = int(round(max(0, min(src_rows - 1, src_row_f))))
        warped[row, :] = depth_ds[src_row, :]

    rgba = _depth_to_rgba(warped)
    img = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
