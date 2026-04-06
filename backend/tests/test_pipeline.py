import numpy as np
import pytest
from tsunami.simulation.okada import FaultParams, magnitude_to_fault_params, compute_displacement
from tsunami.simulation.grid import create_grid, domain_for_magnitude
from tsunami.bathymetry.procedural import generate_continental_shelf
from tsunami.simulation.swe_solver import SWESolverConfig, SWEState, run_swe
from tsunami.simulation.impact import detect_coastal_impacts, suggest_focus_zones
from tsunami.simulation.boussinesq import (
    BoussinesqConfig,
    create_boundary_conditions_from_swe,
    run_boussinesq,
)
from tsunami.simulation.inundation import compute_inundation


class TestFullPipeline:
    def test_earthquake_to_inundation(self):
        """Run the complete pipeline with procedural bathymetry."""
        # 1. Define earthquake
        lat, lon, mag, direction = 0.0, 100.0, 8.0, 270.0

        # 2. Create coarse grid
        bounds = domain_for_magnitude(lat, lon, mag)
        coarse_grid = create_grid(
            lat_min=max(bounds["lat_min"], -5.0),
            lat_max=min(bounds["lat_max"], 5.0),
            lon_min=max(bounds["lon_min"], 95.0),
            lon_max=min(bounds["lon_max"], 105.0),
            resolution_km=50.0,
        )

        # 3. Generate bathymetry with coast on west side
        depth = generate_continental_shelf(
            coarse_grid,
            coast_lon=95.5,
            shelf_width_km=100.0,
            shelf_depth_m=200.0,
            ocean_depth_m=4000.0,
        )
        coarse_grid = coarse_grid.with_depth(depth)

        # 4. Compute seafloor displacement
        fault = magnitude_to_fault_params(lat, lon, mag, direction)
        displacement = compute_displacement(fault, coarse_grid)
        assert np.max(np.abs(displacement)) > 0.1

        # 5. Run coarse SWE
        config = SWESolverConfig(
            duration_seconds=1800.0,
            output_interval_seconds=600.0,
            cfl=0.4,
        )
        coarse_frames: list[tuple[float, SWEState]] = []

        def save_frame(t: float, state: SWEState):
            coarse_frames.append((t, SWEState(
                eta=state.eta.copy(), hu=state.hu.copy(), hv=state.hv.copy(),
            )))

        final_state = run_swe(coarse_grid, displacement, config, frame_callback=save_frame)
        assert len(coarse_frames) >= 2

        # 6. Detect coastal impacts
        max_heights = np.zeros(coarse_grid.depth.shape)
        for _, state in coarse_frames:
            np.maximum(max_heights, np.abs(state.eta), out=max_heights)

        impacts = detect_coastal_impacts(
            coarse_grid, max_heights,
            depth_threshold=300.0, height_threshold=0.1,
        )
        assert isinstance(impacts, list)

        # 7. If we have impacts, run detailed analysis on a focus zone
        if len(impacts) > 0:
            zones = suggest_focus_zones(impacts, cluster_radius_km=200.0)
            assert len(zones) > 0
            zone = zones[0]

            fine_grid = create_grid(
                lat_min=zone.lat_min,
                lat_max=zone.lat_max,
                lon_min=zone.lon_min,
                lon_max=zone.lon_max,
                resolution_km=5.0,
            )
            fine_depth = generate_continental_shelf(
                fine_grid,
                coast_lon=zone.lon_min + 0.1,
                shelf_width_km=30.0,
                shelf_depth_m=50.0,
                ocean_depth_m=200.0,
            )
            fine_grid = fine_grid.with_depth(fine_depth)

            # Extract boundary conditions
            bc = create_boundary_conditions_from_swe(
                coarse_grid, fine_grid, coarse_frames,
            )

            # Run Boussinesq
            bous_config = BoussinesqConfig(
                duration_seconds=300.0,
                output_interval_seconds=150.0,
                cfl=0.3,
            )
            initial_eta = np.zeros(fine_grid.depth.shape)
            result = run_boussinesq(
                fine_grid, initial_eta, bous_config,
                boundary_conditions=bc,
            )

            # 8. Compute inundation
            inundation = compute_inundation(
                fine_grid, result.max_wave_heights, result.max_velocity,
            )
            assert inundation.flood_depth.shape == fine_grid.depth.shape

            # Generate GeoJSON
            geojson = inundation.inundation_extent_geojson()
            assert "type" in geojson

    def test_pipeline_with_zero_magnitude_produces_no_effect(self):
        """Sanity check: zero slip means no waves."""
        grid = create_grid(
            lat_min=-2.0, lat_max=2.0,
            lon_min=98.0, lon_max=102.0,
            resolution_km=50.0,
        )
        depth = np.full(grid.depth.shape, 4000.0)
        grid = grid.with_depth(depth)

        params = FaultParams(
            lat=0.0, lon=100.0,
            strike=0.0, dip=15.0, rake=90.0,
            slip_m=0.0, length_km=100.0, width_km=50.0, depth_km=10.0,
        )
        displacement = compute_displacement(params, grid)
        assert np.allclose(displacement, 0.0)

        config = SWESolverConfig(duration_seconds=300.0, output_interval_seconds=300.0)
        final = run_swe(grid, displacement, config)
        assert np.max(np.abs(final.eta)) < 1e-10
