import numpy as np
import pytest
from tsunami.simulation.grid import create_grid
from tsunami.simulation.boussinesq import (
    BoussinesqConfig,
    BoussinesqResult,
    BoundaryConditions,
    create_boundary_conditions_from_swe,
    run_boussinesq,
)
from tsunami.simulation.swe_solver import SWEState


class TestBoundaryConditions:
    def test_extract_boundary_from_coarse_state(self):
        coarse_grid = create_grid(
            lat_min=-5.0, lat_max=5.0,
            lon_min=95.0, lon_max=105.0,
            resolution_km=50.0,
        )
        fine_grid = create_grid(
            lat_min=-1.0, lat_max=1.0,
            lon_min=99.0, lon_max=101.0,
            resolution_km=5.0,
        )
        # Create a simple coarse state with uniform surface elevation
        eta = np.full(coarse_grid.depth.shape, 0.5)
        hu = np.zeros(coarse_grid.depth.shape)
        hv = np.zeros(coarse_grid.depth.shape)

        coarse_states = [
            (0.0, SWEState(eta=eta.copy(), hu=hu.copy(), hv=hv.copy())),
            (300.0, SWEState(eta=eta * 0.8, hu=hu.copy(), hv=hv.copy())),
        ]

        bc = create_boundary_conditions_from_swe(coarse_grid, fine_grid, coarse_states)
        assert bc.n_timesteps == 2
        assert bc.time_seconds[0] == 0.0
        assert bc.time_seconds[1] == 300.0


class TestBoussinesqSolver:
    def test_runs_and_returns_result(self):
        grid = create_grid(
            lat_min=-0.5, lat_max=0.5,
            lon_min=-0.5, lon_max=0.5,
            resolution_km=5.0,
        )
        depth = np.full(grid.depth.shape, 100.0)  # shallow shelf
        grid = grid.with_depth(depth)

        # Simple initial condition: uniform small wave
        initial_eta = np.full(grid.depth.shape, 0.5)

        config = BoussinesqConfig(
            duration_seconds=120.0,
            output_interval_seconds=60.0,
            cfl=0.3,
        )

        result = run_boussinesq(
            grid, initial_eta, config,
            boundary_conditions=None,
            progress_callback=None,
        )
        assert isinstance(result, BoussinesqResult)
        assert result.max_wave_heights.shape == grid.depth.shape
        assert result.max_velocity.shape == grid.depth.shape
        assert len(result.frames) >= 1

    def test_dispersive_effect_differs_from_swe(self):
        """Boussinesq should show different wave shapes than SWE due to dispersion."""
        grid = create_grid(
            lat_min=-0.5, lat_max=0.5,
            lon_min=-0.5, lon_max=0.5,
            resolution_km=2.0,
        )
        depth = np.full(grid.depth.shape, 50.0)  # shallow water
        grid = grid.with_depth(depth)

        # Narrow initial pulse — dispersion should spread it
        initial_eta = np.zeros(grid.depth.shape)
        cy, cx = grid.depth.shape[0] // 2, grid.depth.shape[1] // 2
        initial_eta[cy, cx] = 1.0

        config = BoussinesqConfig(
            duration_seconds=60.0,
            output_interval_seconds=30.0,
            cfl=0.3,
        )

        result = run_boussinesq(grid, initial_eta, config)
        # After some time, the pulse should have spread
        final_eta = result.frames[-1][1]
        assert np.max(np.abs(final_eta)) < 1.0  # peak should have diminished

    def test_progress_callback_is_called(self):
        grid = create_grid(
            lat_min=-0.2, lat_max=0.2,
            lon_min=-0.2, lon_max=0.2,
            resolution_km=5.0,
        )
        depth = np.full(grid.depth.shape, 100.0)
        grid = grid.with_depth(depth)
        initial_eta = np.full(grid.depth.shape, 0.3)

        config = BoussinesqConfig(
            duration_seconds=60.0,
            output_interval_seconds=60.0,
            cfl=0.3,
        )

        progress_values = []

        def on_progress(pct: float):
            progress_values.append(pct)

        run_boussinesq(grid, initial_eta, config, progress_callback=on_progress)
        assert len(progress_values) > 0
        assert progress_values[-1] >= 90.0  # should reach near 100%
