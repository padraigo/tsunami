"""Coastal impact detection and focus zone suggestion."""

from dataclasses import dataclass
import numpy as np
from tsunami.simulation.grid import Grid, METERS_PER_DEG_LAT


@dataclass
class CoastalImpact:
    lat: float
    lon: float
    max_height: float  # meters
    arrival_time_s: float


@dataclass
class FocusZoneSuggestion:
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    max_impact_height: float
    impact_count: int


def detect_coastal_impacts(
    grid: Grid,
    eta: np.ndarray,
    depth_threshold: float = 200.0,
    height_threshold: float = 1.0,
    arrival_time_s: float = 0.0,
) -> list[CoastalImpact]:
    """Find grid cells where wave height exceeds threshold at coastal locations.

    Coastal cells are those with depth < depth_threshold.
    """
    impacts = []
    ny, nx = grid.depth.shape
    for j in range(ny):
        for k in range(nx):
            if grid.depth[j, k] < depth_threshold and abs(eta[j, k]) >= height_threshold:
                impacts.append(CoastalImpact(
                    lat=float(grid.lat[j]),
                    lon=float(grid.lon[k]),
                    max_height=float(abs(eta[j, k])),
                    arrival_time_s=arrival_time_s,
                ))
    return impacts


def suggest_focus_zones(
    impacts: list[CoastalImpact],
    cluster_radius_km: float = 100.0,
    padding_deg: float = 0.5,
) -> list[FocusZoneSuggestion]:
    """Cluster impacts into rectangular focus zones using greedy distance-based clustering."""
    if not impacts:
        return []

    remaining = list(impacts)
    clusters: list[list[CoastalImpact]] = []

    while remaining:
        seed = remaining.pop(0)
        cluster = [seed]
        still_remaining = []
        for imp in remaining:
            if _haversine_km(seed.lat, seed.lon, imp.lat, imp.lon) <= cluster_radius_km:
                cluster.append(imp)
            else:
                still_remaining.append(imp)
        remaining = still_remaining
        clusters.append(cluster)

    zones = []
    for cluster in clusters:
        lats = [imp.lat for imp in cluster]
        lons = [imp.lon for imp in cluster]
        zones.append(FocusZoneSuggestion(
            lat_min=min(lats) - padding_deg,
            lat_max=max(lats) + padding_deg,
            lon_min=min(lons) - padding_deg,
            lon_max=max(lons) + padding_deg,
            max_impact_height=max(imp.max_height for imp in cluster),
            impact_count=len(cluster),
        ))

    zones.sort(key=lambda z: z.max_impact_height, reverse=True)
    return zones


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance between two points in km."""
    dy = (lat2 - lat1) * METERS_PER_DEG_LAT
    avg_lat = (lat1 + lat2) / 2
    dx = (lon2 - lon1) * METERS_PER_DEG_LAT * np.cos(np.radians(avg_lat))
    return float(np.sqrt(dx**2 + dy**2)) / 1000.0
