"""Procedural bathymetry generation for testing and demos."""

import numpy as np
from tsunami.simulation.grid import Grid, METERS_PER_DEG_LAT


def generate_ocean_basin(grid, depth_m=4000.0):
    return np.full(grid.depth.shape, depth_m)


def generate_continental_shelf(grid, coast_lon, shelf_width_km=100.0, shelf_depth_m=200.0,
                                ocean_depth_m=4000.0, slope_width_km=50.0):
    center_lat = (grid.lat[0] + grid.lat[-1]) / 2
    meters_per_deg_lon = METERS_PER_DEG_LAT * np.cos(np.radians(center_lat))
    dist_km = (grid.lon - coast_lon) * meters_per_deg_lon / 1000.0

    depth_1d = np.full_like(grid.lon, ocean_depth_m)
    for i, d in enumerate(dist_km):
        if d < 0:
            depth_1d[i] = max(0.0, shelf_depth_m * (1 + d / 10.0))
        elif d < shelf_width_km:
            depth_1d[i] = shelf_depth_m
        elif d < shelf_width_km + slope_width_km:
            t = (d - shelf_width_km) / slope_width_km
            t_smooth = (1 - np.cos(t * np.pi)) / 2
            depth_1d[i] = shelf_depth_m + (ocean_depth_m - shelf_depth_m) * t_smooth

    depth_1d = np.maximum(depth_1d, 0.0)
    return np.broadcast_to(depth_1d, grid.depth.shape).copy()


def generate_procedural_bathymetry(grid):
    coast_lon = grid.lon[0] + (grid.lon[-1] - grid.lon[0]) * 0.1
    depth = generate_continental_shelf(
        grid, coast_lon=coast_lon, shelf_width_km=80.0,
        shelf_depth_m=200.0, ocean_depth_m=4000.0,
    )
    return grid.with_depth(depth)
