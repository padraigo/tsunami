import numpy as np
import pytest
from tsunami.simulation.grid import Grid, create_grid
from tsunami.simulation.impact import (
    CoastalImpact,
    FocusZoneSuggestion,
    detect_coastal_impacts,
    suggest_focus_zones,
)


class TestDetectCoastalImpacts:
    def test_finds_impacts_above_threshold(self):
        grid = create_grid(lat_min=0.0, lat_max=2.0, lon_min=0.0, lon_max=2.0, resolution_km=50.0)
        depth = np.full(grid.depth.shape, 4000.0)
        # Create a coastal strip (shallow cells along the east edge)
        depth[:, -3:] = 50.0
        grid = grid.with_depth(depth)

        eta = np.zeros(grid.depth.shape)
        # Place a large wave on the coastal strip
        eta[:, -2] = 3.0

        impacts = detect_coastal_impacts(grid, eta, depth_threshold=200.0, height_threshold=1.0)
        assert len(impacts) > 0
        assert all(imp.max_height >= 1.0 for imp in impacts)

    def test_no_impacts_below_threshold(self):
        grid = create_grid(lat_min=0.0, lat_max=1.0, lon_min=0.0, lon_max=1.0, resolution_km=50.0)
        depth = np.full(grid.depth.shape, 50.0)
        grid = grid.with_depth(depth)

        eta = np.full(grid.depth.shape, 0.1)  # small waves everywhere

        impacts = detect_coastal_impacts(grid, eta, depth_threshold=200.0, height_threshold=1.0)
        assert len(impacts) == 0


class TestSuggestFocusZones:
    def test_clusters_nearby_impacts(self):
        impacts = [
            CoastalImpact(lat=0.0, lon=0.0, max_height=2.0, arrival_time_s=0.0),
            CoastalImpact(lat=0.1, lon=0.1, max_height=1.5, arrival_time_s=0.0),
            CoastalImpact(lat=5.0, lon=5.0, max_height=3.0, arrival_time_s=0.0),
        ]
        zones = suggest_focus_zones(impacts, cluster_radius_km=100.0)
        assert len(zones) == 2  # two clusters: (0,0)+(0.1,0.1) and (5,5)

    def test_zone_bounds_contain_impacts(self):
        impacts = [
            CoastalImpact(lat=1.0, lon=2.0, max_height=2.0, arrival_time_s=0.0),
            CoastalImpact(lat=1.5, lon=2.5, max_height=1.0, arrival_time_s=0.0),
        ]
        zones = suggest_focus_zones(impacts, cluster_radius_km=200.0)
        assert len(zones) == 1
        z = zones[0]
        assert z.lat_min <= 1.0 and z.lat_max >= 1.5
        assert z.lon_min <= 2.0 and z.lon_max >= 2.5

    def test_empty_impacts_gives_no_zones(self):
        zones = suggest_focus_zones([], cluster_radius_km=100.0)
        assert len(zones) == 0
