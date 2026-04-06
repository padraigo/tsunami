import numpy as np
import pytest
from tsunami.simulation.grid import create_grid
from tsunami.simulation.inundation import (
    InundationResult,
    compute_inundation,
)


class TestComputeInundation:
    def _make_coastal_grid(self):
        """Create a grid with coastal topography: ocean -> beach -> land."""
        grid = create_grid(
            lat_min=-0.5, lat_max=0.5,
            lon_min=-0.5, lon_max=0.5,
            resolution_km=5.0,
        )
        ny, nx = grid.depth.shape
        # Depth profile: deep ocean on left, sloping to land (negative depth = elevation)
        depth = np.zeros((ny, nx))
        for j in range(nx):
            frac = j / (nx - 1)
            # From 100m deep to 20m above sea level
            depth[:, j] = 100.0 - 120.0 * frac
        return grid.with_depth(depth)

    def test_inundation_detected_on_land(self):
        grid = self._make_coastal_grid()
        ny, nx = grid.depth.shape

        # Wave that floods some land
        max_heights = np.zeros((ny, nx))
        max_heights[:, :] = 5.0  # 5m waves everywhere

        max_velocity = np.ones((ny, nx)) * 2.0

        result = compute_inundation(grid, max_heights, max_velocity)
        assert isinstance(result, InundationResult)
        # Some cells should be inundated (where depth < 0 but wave > |depth|)
        assert np.any(result.flood_depth > 0)
        assert result.max_runup_m > 0

    def test_no_inundation_with_small_waves(self):
        grid = self._make_coastal_grid()
        ny, nx = grid.depth.shape

        max_heights = np.full((ny, nx), 0.01)  # tiny waves
        max_velocity = np.full((ny, nx), 0.01)

        result = compute_inundation(grid, max_heights, max_velocity)
        # Waves too small to reach land
        assert result.max_runup_m < 1.0

    def test_flood_depth_is_wave_minus_elevation(self):
        grid = create_grid(
            lat_min=0.0, lat_max=0.1,
            lon_min=0.0, lon_max=0.1,
            resolution_km=2.0,
        )
        # Single elevation: 3m above sea level (depth = -3)
        depth = np.full(grid.depth.shape, -3.0)
        grid = grid.with_depth(depth)

        # 5m wave -> flood depth should be ~2m
        max_heights = np.full(grid.depth.shape, 5.0)
        max_velocity = np.ones(grid.depth.shape)

        result = compute_inundation(grid, max_heights, max_velocity)
        # Flood depth = wave height - elevation = 5 - 3 = 2m
        assert np.allclose(result.flood_depth, 2.0, atol=0.1)

    def test_geojson_polygon_generated(self):
        grid = self._make_coastal_grid()
        max_heights = np.full(grid.depth.shape, 5.0)
        max_velocity = np.ones(grid.depth.shape) * 2.0

        result = compute_inundation(grid, max_heights, max_velocity)
        geojson = result.inundation_extent_geojson()
        assert geojson["type"] == "Feature"
        assert geojson["geometry"]["type"] in ("Polygon", "MultiPolygon")
