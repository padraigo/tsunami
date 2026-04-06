"""Grid creation, coordinate transforms, and resampling for simulation domains."""

from dataclasses import dataclass
import numpy as np
from scipy.interpolate import RegularGridInterpolator

EARTH_RADIUS_KM = 6371.0
METERS_PER_DEG_LAT = 111_320.0


@dataclass(frozen=True)
class Grid:
    """2D simulation grid in lat/lon coordinates.

    lat: 1D array of latitude values (south to north), shape (ny,)
    lon: 1D array of longitude values (west to east), shape (nx,)
    depth: 2D array of ocean depth in meters (positive down), shape (ny, nx)
    """
    lat: np.ndarray
    lon: np.ndarray
    depth: np.ndarray

    def with_depth(self, depth: np.ndarray) -> "Grid":
        if depth.shape != self.depth.shape:
            raise ValueError(f"Depth shape {depth.shape} doesn't match grid shape {self.depth.shape}")
        return Grid(lat=self.lat, lon=self.lon, depth=depth)

    def to_meters(self) -> tuple[np.ndarray, np.ndarray]:
        lat_ref = (self.lat[0] + self.lat[-1]) / 2
        meters_per_deg_lon = METERS_PER_DEG_LAT * np.cos(np.radians(lat_ref))
        y = (self.lat - self.lat[0]) * METERS_PER_DEG_LAT
        x = (self.lon - self.lon[0]) * meters_per_deg_lon
        return x, y

    def cell_size_m(self) -> tuple[float, float]:
        x, y = self.to_meters()
        dx = x[1] - x[0] if len(x) > 1 else 0.0
        dy = y[1] - y[0] if len(y) > 1 else 0.0
        return float(dx), float(dy)


def create_grid(lat_min, lat_max, lon_min, lon_max, resolution_km):
    center_lat = (lat_min + lat_max) / 2
    dlat = resolution_km / (EARTH_RADIUS_KM * np.radians(1))
    dlon = dlat / np.cos(np.radians(center_lat))
    lat = np.arange(lat_min, lat_max + dlat / 2, dlat)
    lon = np.arange(lon_min, lon_max + dlon / 2, dlon)
    depth = np.zeros((len(lat), len(lon)))
    return Grid(lat=lat, lon=lon, depth=depth)


def domain_for_magnitude(lat, lon, magnitude):
    radius_deg = 10.0 * (10 ** ((magnitude - 7.0) * 0.5))
    radius_deg = min(radius_deg, 80.0)
    return {
        "lat_min": max(lat - radius_deg / 2, -90.0),
        "lat_max": min(lat + radius_deg / 2, 90.0),
        "lon_min": lon - radius_deg / 2,
        "lon_max": lon + radius_deg / 2,
    }


def resample_grid(grid, target_resolution_km):
    new_grid = create_grid(
        lat_min=float(grid.lat[0]), lat_max=float(grid.lat[-1]),
        lon_min=float(grid.lon[0]), lon_max=float(grid.lon[-1]),
        resolution_km=target_resolution_km,
    )
    interpolator = RegularGridInterpolator(
        (grid.lat, grid.lon), grid.depth, method="linear",
        bounds_error=False, fill_value=None,
    )
    lat_2d, lon_2d = np.meshgrid(new_grid.lat, new_grid.lon, indexing="ij")
    points = np.column_stack([lat_2d.ravel(), lon_2d.ravel()])
    new_depth = interpolator(points).reshape(lat_2d.shape)
    return new_grid.with_depth(new_depth)
