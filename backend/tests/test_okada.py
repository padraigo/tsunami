import numpy as np
import pytest
from tsunami.simulation.okada import (
    FaultParams,
    magnitude_to_fault_params,
    compute_displacement,
)
from tsunami.simulation.grid import create_grid


class TestWellsCoppersmith:
    def test_m7_fault_dimensions(self):
        params = magnitude_to_fault_params(lat=0.0, lon=100.0, magnitude=7.0, direction=0.0)
        assert 30.0 < params.length_km < 80.0
        assert 10.0 < params.width_km < 40.0
        assert 0.5 < params.slip_m < 4.0

    def test_m9_fault_dimensions(self):
        params = magnitude_to_fault_params(lat=0.0, lon=100.0, magnitude=9.0, direction=0.0)
        assert 300.0 < params.length_km < 1200.0
        assert 50.0 < params.width_km < 250.0
        assert 5.0 < params.slip_m < 30.0

    def test_direction_sets_strike(self):
        params = magnitude_to_fault_params(lat=0.0, lon=100.0, magnitude=8.0, direction=45.0)
        assert params.strike == 45.0

    def test_default_dip_for_subduction(self):
        params = magnitude_to_fault_params(lat=0.0, lon=100.0, magnitude=8.0, direction=0.0)
        assert 5.0 < params.dip < 30.0


class TestOkadaDisplacement:
    def test_displacement_is_nonzero_near_fault(self):
        params = FaultParams(
            lat=0.0, lon=100.0, strike=0.0, dip=15.0, rake=90.0,
            slip_m=5.0, length_km=200.0, width_km=80.0, depth_km=10.0,
        )
        grid = create_grid(lat_min=-3.0, lat_max=3.0, lon_min=97.0, lon_max=103.0, resolution_km=10.0)
        disp = compute_displacement(params, grid)
        assert disp.shape == grid.depth.shape
        assert np.max(disp) > 0.0
        assert np.min(disp) < 0.0

    def test_displacement_decays_with_distance(self):
        params = FaultParams(
            lat=0.0, lon=100.0, strike=0.0, dip=15.0, rake=90.0,
            slip_m=5.0, length_km=200.0, width_km=80.0, depth_km=10.0,
        )
        grid = create_grid(lat_min=-10.0, lat_max=10.0, lon_min=90.0, lon_max=110.0, resolution_km=20.0)
        disp = compute_displacement(params, grid)
        center_row = disp.shape[0] // 2
        center_col = disp.shape[1] // 2
        near_center = np.abs(disp[center_row, center_col])
        at_edge = np.abs(disp[0, 0])
        assert near_center > at_edge * 5

    def test_pure_thrust_produces_uplift_on_hanging_wall(self):
        params = FaultParams(
            lat=0.0, lon=100.0, strike=0.0, dip=15.0, rake=90.0,
            slip_m=5.0, length_km=200.0, width_km=80.0, depth_km=10.0,
        )
        grid = create_grid(lat_min=-3.0, lat_max=3.0, lon_min=97.0, lon_max=103.0, resolution_km=5.0)
        disp = compute_displacement(params, grid)
        max_idx = np.unravel_index(np.argmax(disp), disp.shape)
        assert max_idx[1] > disp.shape[1] // 3

    def test_zero_slip_gives_zero_displacement(self):
        params = FaultParams(
            lat=0.0, lon=100.0, strike=0.0, dip=15.0, rake=90.0,
            slip_m=0.0, length_km=200.0, width_km=80.0, depth_km=10.0,
        )
        grid = create_grid(lat_min=-1.0, lat_max=1.0, lon_min=99.0, lon_max=101.0, resolution_km=20.0)
        disp = compute_displacement(params, grid)
        assert np.allclose(disp, 0.0)
