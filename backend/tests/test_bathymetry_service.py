import numpy as np
import pytest
from tsunami.simulation.grid import create_grid
from tsunami.bathymetry.service import BathymetryService


class TestBathymetryService:
    def test_get_bathymetry_procedural_fallback(self):
        service = BathymetryService(cache_dir="/tmp/tsunami_bathy_test")
        grid = create_grid(
            lat_min=-2.0, lat_max=2.0,
            lon_min=98.0, lon_max=102.0,
            resolution_km=50.0,
        )
        result = service.get_bathymetry(grid, source="procedural")
        assert result.shape == grid.depth.shape
        assert np.any(result > 0)  # should have some ocean depth

    def test_check_availability_procedural_always_available(self):
        service = BathymetryService(cache_dir="/tmp/tsunami_bathy_test")
        avail = service.check_availability(
            lat_min=-2.0, lat_max=2.0, lon_min=98.0, lon_max=102.0,
        )
        assert avail["procedural"] is True

    def test_get_bathymetry_returns_correct_shape(self):
        service = BathymetryService(cache_dir="/tmp/tsunami_bathy_test")
        grid = create_grid(
            lat_min=0.0, lat_max=1.0,
            lon_min=0.0, lon_max=1.0,
            resolution_km=20.0,
        )
        result = service.get_bathymetry(grid, source="procedural")
        assert result.shape == grid.depth.shape
