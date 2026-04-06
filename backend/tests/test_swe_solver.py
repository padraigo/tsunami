import numpy as np
import pytest
from tsunami.simulation.grid import Grid, create_grid
from tsunami.simulation.swe_solver import (
    SWEState,
    SWESolverConfig,
    create_initial_state,
    compute_cfl_dt,
    swe_step,
    run_swe,
)


class TestSWEState:
    def test_create_initial_state_from_displacement(self):
        grid = create_grid(lat_min=-1.0, lat_max=1.0, lon_min=-1.0, lon_max=1.0, resolution_km=20.0)
        depth = np.full(grid.depth.shape, 4000.0)
        grid = grid.with_depth(depth)
        displacement = np.zeros(grid.depth.shape)
        displacement[5, 5] = 2.0
        state = create_initial_state(grid, displacement)
        assert state.eta.shape == grid.depth.shape
        assert state.hu.shape == grid.depth.shape
        assert state.hv.shape == grid.depth.shape
        assert np.allclose(state.eta, displacement)
        assert np.allclose(state.hu, 0.0)
        assert np.allclose(state.hv, 0.0)


class TestCFLTimestep:
    def test_cfl_dt_shallow_water(self):
        dx = 2000.0
        max_depth = 4000.0
        dt = compute_cfl_dt(dx, dx, max_depth, cfl=0.5)
        assert 3.0 < dt < 8.0

    def test_cfl_dt_respects_smaller_dimension(self):
        dt1 = compute_cfl_dt(2000.0, 2000.0, 4000.0, cfl=0.5)
        dt2 = compute_cfl_dt(1000.0, 2000.0, 4000.0, cfl=0.5)
        assert dt2 < dt1


class TestSWEStep:
    def test_single_step_conserves_mass_approximately(self):
        grid = create_grid(lat_min=-1.0, lat_max=1.0, lon_min=-1.0, lon_max=1.0, resolution_km=20.0)
        depth = np.full(grid.depth.shape, 4000.0)
        grid = grid.with_depth(depth)
        displacement = np.zeros(grid.depth.shape)
        cy, cx = grid.depth.shape[0] // 2, grid.depth.shape[1] // 2
        for i in range(grid.depth.shape[0]):
            for j in range(grid.depth.shape[1]):
                r2 = (i - cy) ** 2 + (j - cx) ** 2
                displacement[i, j] = 2.0 * np.exp(-r2 / 8.0)
        state = create_initial_state(grid, displacement)
        mass_before = np.sum(state.eta)
        dx, dy = grid.cell_size_m()
        dt = compute_cfl_dt(dx, dy, float(np.max(depth)), cfl=0.4)
        new_state = swe_step(state, grid, dt)
        mass_after = np.sum(new_state.eta)
        assert abs(mass_after - mass_before) / abs(mass_before) < 0.01


class TestRunSWE:
    def test_wave_propagates_outward(self):
        grid = create_grid(lat_min=-2.0, lat_max=2.0, lon_min=-2.0, lon_max=2.0, resolution_km=20.0)
        depth = np.full(grid.depth.shape, 4000.0)
        grid = grid.with_depth(depth)
        displacement = np.zeros(grid.depth.shape)
        cy, cx = grid.depth.shape[0] // 2, grid.depth.shape[1] // 2
        for i in range(grid.depth.shape[0]):
            for j in range(grid.depth.shape[1]):
                r2 = (i - cy) ** 2 + (j - cx) ** 2
                displacement[i, j] = 2.0 * np.exp(-r2 / 4.0)
        config = SWESolverConfig(duration_seconds=600.0, output_interval_seconds=300.0, cfl=0.4)
        frames = []
        def callback(time_s, state):
            frames.append((time_s, state.eta.copy()))
        run_swe(grid, displacement, config, frame_callback=callback)
        assert len(frames) >= 2
        initial_center = np.abs(displacement[cy, cx])
        final_center = np.abs(frames[-1][1][cy, cx])
        assert final_center < initial_center

    def test_flat_ocean_no_displacement_stays_calm(self):
        grid = create_grid(lat_min=-1.0, lat_max=1.0, lon_min=-1.0, lon_max=1.0, resolution_km=20.0)
        depth = np.full(grid.depth.shape, 4000.0)
        grid = grid.with_depth(depth)
        displacement = np.zeros(grid.depth.shape)
        config = SWESolverConfig(duration_seconds=300.0, output_interval_seconds=300.0, cfl=0.4)
        frames = []
        def callback(time_s, state):
            frames.append((time_s, state.eta.copy()))
        run_swe(grid, displacement, config, frame_callback=callback)
        assert np.max(np.abs(frames[-1][1])) < 1e-10
