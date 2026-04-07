"""Simplified harmonic tidal model.

Computes tide heights using the four dominant tidal constituents (M2, S2, K1, O1)
with equilibrium tide spatial patterns. Good enough for visualization and
approximate tide-tsunami interaction, not for navigation.
"""

from datetime import datetime, timezone
import numpy as np


# Tidal constituents: period (hours), equilibrium amplitude (meters), type
CONSTITUENTS = {
    "M2": {"period_h": 12.4206, "amp_m": 0.24, "type": "semidiurnal"},
    "S2": {"period_h": 12.0000, "amp_m": 0.11, "type": "semidiurnal"},
    "K1": {"period_h": 23.9345, "amp_m": 0.14, "type": "diurnal"},
    "O1": {"period_h": 25.8193, "amp_m": 0.10, "type": "diurnal"},
}


def _julian_centuries(dt: datetime) -> float:
    """Julian centuries from J2000.0 epoch."""
    # J2000.0 = 2000-01-01 12:00:00 UTC = JD 2451545.0
    j2000 = datetime(2000, 1, 12, 0, 0, tzinfo=timezone.utc)
    delta = dt.replace(tzinfo=timezone.utc) - j2000
    jd_offset = delta.total_seconds() / 86400.0
    return jd_offset / 36525.0


def _astronomical_arguments(dt: datetime) -> dict[str, float]:
    """Compute astronomical arguments for tidal phase calculation.

    Returns angles in degrees for the Moon and Sun positions.
    Simplified from Meeus, Astronomical Algorithms.
    """
    T = _julian_centuries(dt)
    s = (218.3165 + 481267.8813 * T) % 360  # Moon's mean longitude
    h = (280.4661 + 36000.7698 * T) % 360   # Sun's mean longitude
    p = (83.3532 + 4069.0137 * T) % 360     # Lunar perigee
    N = (125.0445 - 1934.1363 * T) % 360    # Lunar node
    return {"s": s, "h": h, "p": p, "N": N, "T": T}


def _constituent_phase(name: str, args: dict[str, float]) -> float:
    """Compute the astronomical phase (V0) for a tidal constituent in degrees."""
    s, h = args["s"], args["h"]
    if name == "M2":
        return (2 * h - 2 * s) % 360
    elif name == "S2":
        return 0.0  # Phase relative to solar time
    elif name == "K1":
        return (h + 90.0) % 360
    elif name == "O1":
        return (h - 2 * s - 90.0) % 360
    return 0.0


def compute_tide_field(
    lat: np.ndarray,
    lon: np.ndarray,
    dt: datetime,
) -> np.ndarray:
    """Compute tidal height at each grid point for a given UTC datetime.

    Args:
        lat: 1D array of latitudes (degrees).
        lon: 1D array of longitudes (degrees).
        dt: UTC datetime.

    Returns:
        2D array of tide heights in meters, shape (len(lat), len(lon)).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    args = _astronomical_arguments(dt)
    hours = dt.hour + dt.minute / 60.0 + dt.second / 3600.0

    lat2d, lon2d = np.meshgrid(lat, lon, indexing="ij")
    lat_rad = np.radians(lat2d)
    total = np.zeros_like(lat2d, dtype=np.float64)

    for name, c in CONSTITUENTS.items():
        omega = 2 * np.pi / c["period_h"]  # rad/hour
        V0 = _constituent_phase(name, args)

        # Spatial amplitude (equilibrium tide pattern)
        if c["type"] == "semidiurnal":
            spatial = c["amp_m"] * np.cos(lat_rad) ** 2
            phase = np.radians(V0) + omega * hours + 2 * np.radians(lon2d)
        else:  # diurnal
            spatial = c["amp_m"] * np.sin(2 * lat_rad)
            phase = np.radians(V0) + omega * hours + np.radians(lon2d)

        total += spatial * np.cos(phase)

    return total


def generate_tide_frames(
    lat: np.ndarray,
    lon: np.ndarray,
    start_dt: datetime,
    duration_hours: float = 25.0,
    num_frames: int = 50,
) -> list[tuple[float, np.ndarray]]:
    """Generate a time series of tidal height fields for animation.

    Args:
        lat: 1D latitude array.
        lon: 1D longitude array.
        start_dt: Start UTC datetime.
        duration_hours: Duration of animation.
        num_frames: Number of frames to generate.

    Returns:
        List of (time_seconds, tide_height_2d) tuples.
    """
    from datetime import timedelta

    frames = []
    dt_step = duration_hours / max(num_frames - 1, 1)

    for i in range(num_frames):
        t_hours = i * dt_step
        dt = start_dt + timedelta(hours=t_hours)
        tide = compute_tide_field(lat, lon, dt)
        frames.append((t_hours * 3600.0, tide))

    return frames
