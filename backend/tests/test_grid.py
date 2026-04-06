import numpy as np
import pytest
from tsunami.simulation.grid import Grid, create_grid, resample_grid, domain_for_magnitude


class TestCreateGrid:
    def test_creates_grid_with_correct_shape(self):
        grid = create_grid(
            lat_min=-5.0, lat_max=5.0,
            lon_min=95.0, lon_max=105.0,
            resolution_km=100.0,
        )
        assert grid.lat.shape[0] >= 10
        assert grid.lon.shape[0] >= 10
        assert grid.depth.shape == (grid.lat.shape[0], grid.lon.shape[0])

    def test_grid_lat_lon_are_monotonic(self):
        grid = create_grid(
            lat_min=-2.0, lat_max=2.0,
            lon_min=100.0, lon_max=104.0,
            resolution_km=50.0,
        )
        assert np.all(np.diff(grid.lat) > 0)
        assert np.all(np.diff(grid.lon) > 0)

    def test_grid_depth_initialized_to_zero(self):
        grid = create_grid(
            lat_min=0.0, lat_max=1.0,
            lon_min=0.0, lon_max=1.0,
            resolution_km=50.0,
        )
        assert np.all(grid.depth == 0.0)

    def test_grid_with_depth_array(self):
        grid = create_grid(
            lat_min=0.0, lat_max=1.0,
            lon_min=0.0, lon_max=1.0,
            resolution_km=50.0,
        )
        depth = np.full(grid.depth.shape, 4000.0)
        grid_with_depth = grid.with_depth(depth)
        assert np.all(grid_with_depth.depth == 4000.0)
        assert grid_with_depth.lat is grid.lat


class TestDomainForMagnitude:
    def test_large_earthquake_gets_large_domain(self):
        bounds = domain_for_magnitude(lat=0.0, lon=100.0, magnitude=9.0)
        lat_span = bounds["lat_max"] - bounds["lat_min"]
        assert lat_span > 40

    def test_moderate_earthquake_gets_smaller_domain(self):
        bounds = domain_for_magnitude(lat=0.0, lon=100.0, magnitude=7.0)
        lat_span = bounds["lat_max"] - bounds["lat_min"]
        assert 10 <= lat_span < 30

    def test_domain_centered_on_epicenter(self):
        bounds = domain_for_magnitude(lat=10.0, lon=50.0, magnitude=8.0)
        center_lat = (bounds["lat_min"] + bounds["lat_max"]) / 2
        center_lon = (bounds["lon_min"] + bounds["lon_max"]) / 2
        assert abs(center_lat - 10.0) < 0.1
        assert abs(center_lon - 50.0) < 0.1


class TestResampleGrid:
    def test_resample_to_coarser_resolution(self):
        fine = create_grid(
            lat_min=0.0, lat_max=2.0,
            lon_min=0.0, lon_max=2.0,
            resolution_km=10.0,
        )
        depth = np.full(fine.depth.shape, 3000.0)
        fine = fine.with_depth(depth)
        coarse = resample_grid(fine, target_resolution_km=50.0)
        assert coarse.lat.shape[0] < fine.lat.shape[0]
        assert coarse.lon.shape[0] < fine.lon.shape[0]
        assert np.allclose(coarse.depth, 3000.0, atol=1.0)


class TestGridCoordinateConversion:
    def test_lat_lon_to_meters(self):
        grid = create_grid(
            lat_min=0.0, lat_max=1.0,
            lon_min=0.0, lon_max=1.0,
            resolution_km=50.0,
        )
        x, y = grid.to_meters()
        # y[-1] may not land exactly at 1° due to grid discretization
        assert abs(y[-1] - 111_320) < 15000
        assert x.shape == (grid.lon.shape[0],)
        assert y.shape == (grid.lat.shape[0],)

    def test_cell_area_km2(self):
        grid = create_grid(
            lat_min=0.0, lat_max=1.0,
            lon_min=0.0, lon_max=1.0,
            resolution_km=100.0,
        )
        dx, dy = grid.cell_size_m()
        area_km2 = (dx * dy) / 1e6
        assert 5000 < area_km2 < 15000
