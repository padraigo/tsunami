"""Cached low-resolution global land mask / depth grid."""

from pathlib import Path

import numpy as np

from tsunami.config import get_settings
from tsunami.simulation.grid import create_grid

_land_mask_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}


def get_land_mask(resolution_km: float) -> tuple[np.ndarray, np.ndarray]:
    """Get or compute a cached low-res global land mask."""
    key = f"{resolution_km:g}"
    if key in _land_mask_cache:
        return _land_mask_cache[key]

    cache_dir = Path(get_settings().bathymetry_cache_dir)
    cache_file = cache_dir / f"land_mask_{key}km.npz"

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
