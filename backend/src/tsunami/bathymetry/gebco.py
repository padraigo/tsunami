"""GEBCO bathymetry data loader.

Reads the GEBCO global grid (NetCDF) and extracts/resamples to a target Grid.
GEBCO uses elevation convention (negative = below sea level), but our Grid uses
depth convention (positive = below sea level), so we negate the values.

Expected file: GEBCO_2024.nc (or similar) with variables:
  - lat: 1D latitude array
  - lon: 1D longitude array
  - elevation: 2D array (lat, lon) in meters (negative = ocean, positive = land)
"""

from pathlib import Path

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from tsunami.simulation.grid import Grid


def load_gebco(nc_path: str | Path, grid: Grid) -> np.ndarray:
    """Load GEBCO data and resample to the target grid.

    Args:
        nc_path: Path to GEBCO NetCDF file.
        grid: Target simulation grid.

    Returns:
        2D depth array (positive = below sea level, negative = above).
    """
    import xarray as xr

    ds = xr.open_dataset(nc_path)

    lat_min, lat_max = float(grid.lat[0]), float(grid.lat[-1])
    lon_min, lon_max = float(grid.lon[0]), float(grid.lon[-1])

    def norm_lon(lon: float) -> float:
        return ((lon + 180) % 360) - 180

    lon_min_n = norm_lon(lon_min)
    lon_max_n = norm_lon(lon_max)

    # Compute stride to avoid loading the full 7GB array for coarse grids.
    # GEBCO is ~15 arcsec ≈ 0.004167°. Our grid spacing in degrees:
    grid_dlat = float(grid.lat[1] - grid.lat[0]) if len(grid.lat) > 1 else 1.0
    gebco_dlat = 1.0 / 240.0  # 15 arcsec
    stride = max(1, int(grid_dlat / gebco_dlat / 2))  # 2x oversample for interpolation

    buf = max(0.5, grid_dlat)
    lat_slice = slice(max(-90, lat_min - buf), min(90, lat_max + buf))

    if lon_min_n > lon_max_n:
        # Domain crosses antimeridian
        ds1 = ds.sel(lat=lat_slice, lon=slice(lon_min_n - buf, 180))
        ds2 = ds.sel(lat=lat_slice, lon=slice(-180, lon_max_n + buf))
        # Stride-subsample before loading into memory
        ds1 = ds1.isel(lat=slice(None, None, stride), lon=slice(None, None, stride))
        ds2 = ds2.isel(lat=slice(None, None, stride), lon=slice(None, None, stride))
        ds1_shifted = ds1.assign_coords(lon=ds1.lon.values)
        ds2_shifted = ds2.assign_coords(lon=ds2.lon.values + 360)
        chunk = xr.concat([ds1_shifted, ds2_shifted], dim='lon')
    else:
        chunk = ds.sel(
            lat=lat_slice,
            lon=slice(max(-180, lon_min_n - buf), min(180, lon_max_n + buf)),
        )
        chunk = chunk.isel(lat=slice(None, None, stride), lon=slice(None, None, stride))

    gebco_lat = chunk.lat.values
    gebco_lon = chunk.lon.values
    elevation = chunk.elevation.values  # (lat, lon), negative = ocean

    ds.close()

    interp = RegularGridInterpolator(
        (gebco_lat, gebco_lon),
        elevation,
        method='linear',
        bounds_error=False,
        fill_value=0.0,
    )

    grid_lons = grid.lon.copy()
    if lon_min_n > lon_max_n:
        grid_lons = np.where(grid_lons < 0, grid_lons + 360, grid_lons)
    else:
        grid_lons = np.array([norm_lon(float(lo)) for lo in grid_lons])

    lat_2d, lon_2d = np.meshgrid(grid.lat, grid_lons, indexing='ij')
    points = np.column_stack([lat_2d.ravel(), lon_2d.ravel()])
    elevation_resampled = interp(points).reshape(lat_2d.shape)

    depth = -elevation_resampled
    return depth.astype(np.float64)
