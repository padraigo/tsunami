"""Inundation mapping — flood extent, depth, and velocity extraction.

Determines where tsunami waves flood land, how deep the flooding is,
and generates GeoJSON boundaries of the inundation zone.
"""

from dataclasses import dataclass
from typing import Any
import numpy as np
from tsunami.simulation.grid import Grid


@dataclass
class InundationResult:
    flood_depth: np.ndarray  # (ny, nx) flood depth on land (m), 0 where not flooded
    flow_velocity: np.ndarray  # (ny, nx) max flow velocity (m/s), 0 where not flooded
    max_runup_m: float  # Maximum elevation reached by water (m above sea level)
    inundated_mask: np.ndarray  # (ny, nx) boolean mask of flooded cells
    grid: Grid

    def inundation_extent_geojson(self) -> dict[str, Any]:
        """Generate a GeoJSON Feature of the inundation boundary."""
        polygons = []
        dy = float(self.grid.lat[1] - self.grid.lat[0]) if len(self.grid.lat) > 1 else 0.01
        dx = float(self.grid.lon[1] - self.grid.lon[0]) if len(self.grid.lon) > 1 else 0.01

        rows, cols = np.where(self.inundated_mask)
        for r, c in zip(rows, cols):
            lat = float(self.grid.lat[r])
            lon = float(self.grid.lon[c])
            poly = [
                [lon - dx / 2, lat - dy / 2],
                [lon + dx / 2, lat - dy / 2],
                [lon + dx / 2, lat + dy / 2],
                [lon - dx / 2, lat + dy / 2],
                [lon - dx / 2, lat - dy / 2],
            ]
            polygons.append([poly])

        if not polygons:
            return {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": []},
                "properties": {"max_runup_m": 0.0},
            }

        return {
            "type": "Feature",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": polygons,
            },
            "properties": {
                "max_runup_m": self.max_runup_m,
                "inundated_cells": int(np.sum(self.inundated_mask)),
            },
        }


def compute_inundation(
    grid: Grid,
    max_wave_heights: np.ndarray,
    max_velocity: np.ndarray,
    min_flood_depth: float = 0.01,
) -> InundationResult:
    """Compute inundation from simulation results.

    Land cells have negative depth values (depth = -elevation).
    A land cell is inundated if the wave height exceeds the elevation.
    """
    # Land cells: depth < 0, elevation = -depth
    elevation = np.where(grid.depth < 0, -grid.depth, 0.0)

    # Flood depth = wave height - elevation (only on land)
    flood_depth = np.maximum(max_wave_heights - elevation, 0.0)

    # Only count cells that are actually on land (depth <= 0)
    is_land = grid.depth <= 0
    flood_depth = np.where(is_land, flood_depth, 0.0)

    # Inundation mask
    inundated = flood_depth > min_flood_depth

    # Flow velocity only in inundated areas
    flow_vel = np.where(inundated, max_velocity, 0.0)

    # Maximum runup: highest elevation that got flooded
    if np.any(inundated):
        max_runup = float(np.max(elevation[inundated]))
    else:
        max_runup = 0.0

    return InundationResult(
        flood_depth=flood_depth,
        flow_velocity=flow_vel,
        max_runup_m=max_runup,
        inundated_mask=inundated,
        grid=grid,
    )
