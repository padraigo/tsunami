import numpy as np
import pytest
from tsunami.simulation.grid import Grid, create_grid
from tsunami.bathymetry.procedural import (
    generate_ocean_basin,
    generate_continental_shelf,
    generate_procedural_bathymetry,
)


class TestOceanBasin:
    def test_uniform_depth(self):
        grid = create_grid(lat_min=-5.0, lat_max=5.0, lon_min=95.0, lon_max=105.0, resolution_km=50.0)
        depth = generate_ocean_basin(grid, depth_m=4000.0)
        assert depth.shape == grid.depth.shape
        assert np.allclose(depth, 4000.0)

    def test_depth_is_positive(self):
        grid = create_grid(lat_min=0.0, lat_max=1.0, lon_min=0.0, lon_max=1.0, resolution_km=10.0)
        depth = generate_ocean_basin(grid, depth_m=3000.0)
        assert np.all(depth > 0)


class TestContinentalShelf:
    def test_shelf_has_shallow_and_deep(self):
        grid = create_grid(lat_min=-5.0, lat_max=5.0, lon_min=95.0, lon_max=105.0, resolution_km=20.0)
        depth = generate_continental_shelf(
            grid, coast_lon=95.5, shelf_width_km=100.0, shelf_depth_m=200.0, ocean_depth_m=4000.0,
        )
        coast_col = np.argmin(np.abs(grid.lon - 95.5))
        assert np.mean(depth[:, coast_col]) < 500.0
        assert np.mean(depth[:, -1]) > 3000.0

    def test_depth_transitions_monotonically(self):
        grid = create_grid(lat_min=0.0, lat_max=1.0, lon_min=95.0, lon_max=105.0, resolution_km=20.0)
        depth = generate_continental_shelf(
            grid, coast_lon=95.0, shelf_width_km=200.0, shelf_depth_m=200.0, ocean_depth_m=4000.0,
        )
        mid_row = depth.shape[0] // 2
        profile = depth[mid_row, :]
        assert profile[-1] > profile[0]


class TestProceduralBathymetry:
    def test_generates_valid_grid(self):
        grid = create_grid(lat_min=-5.0, lat_max=5.0, lon_min=95.0, lon_max=105.0, resolution_km=50.0)
        result = generate_procedural_bathymetry(grid)
        assert isinstance(result, Grid)
        assert result.depth.shape == grid.depth.shape
        assert np.all(result.depth >= 0)
