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

    # GEBCO uses 'elevation' variable; lat/lon as coordinates
    # Handle longitude wrapping: GEBCO lon is -180..180
    # Our grid lon might be outside that range (e.g., -187 or 182 for Pacific domains)
    lat_min, lat_max = float(grid.lat[0]), float(grid.lat[-1])
    lon_min, lon_max = float(grid.lon[0]), float(grid.lon[-1])

    # Normalize query longitudes to -180..180 for GEBCO lookup
    def norm_lon(lon: float) -> float:
        return ((lon + 180) % 360) - 180

    lon_min_n = norm_lon(lon_min)
    lon_max_n = norm_lon(lon_max)

    # Add a buffer of ~0.5 degrees for interpolation edges
    buf = 0.5
    lat_slice = slice(max(-90, lat_min - buf), min(90, lat_max + buf))

    # Handle antimeridian crossing
    if lon_min_n > lon_max_n:
        # Domain crosses antimeridian: load two chunks and concatenate
        ds1 = ds.sel(lat=lat_slice, lon=slice(lon_min_n - buf, 180))
        ds2 = ds.sel(lat=lat_slice, lon=slice(-180, lon_max_n + buf))
        # Shift ds1 longitudes to be continuous with ds2
        ds1_shifted = ds1.assign_coords(lon=ds1.lon.values)
        ds2_shifted = ds2.assign_coords(lon=ds2.lon.values + 360)
        chunk = xr.concat([ds1_shifted, ds2_shifted], dim='lon')
    else:
        chunk = ds.sel(
            lat=lat_slice,
            lon=slice(max(-180, lon_min_n - buf), min(180, lon_max_n + buf)),
        )

    gebco_lat = chunk.lat.values
    gebco_lon = chunk.lon.values
    elevation = chunk.elevation.values  # (lat, lon), negative = ocean

    ds.close()

    # Build interpolator
    interp = RegularGridInterpolator(
        (gebco_lat, gebco_lon),
        elevation,
        method='linear',
        bounds_error=False,
        fill_value=0.0,  # Assume sea level at boundaries
    )

    # Map our grid coordinates to GEBCO's coordinate space
    grid_lons = grid.lon.copy()
    if lon_min_n > lon_max_n:
        # For antimeridian-crossing domains, shift negative lons to match concatenated data
        grid_lons = np.where(grid_lons < 0, grid_lons + 360, grid_lons)
    else:
        # Normalize to match GEBCO range
        grid_lons = np.array([norm_lon(float(lo)) for lo in grid_lons])

    lat_2d, lon_2d = np.meshgrid(grid.lat, grid_lons, indexing='ij')
    points = np.column_stack([lat_2d.ravel(), lon_2d.ravel()])
    elevation_resampled = interp(points).reshape(lat_2d.shape)

    # Convert elevation to depth: negate (ocean becomes positive, land becomes negative)
    depth = -elevation_resampled

    return depth.astype(np.float64)
