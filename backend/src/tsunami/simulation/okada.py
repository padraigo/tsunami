"""Okada (1985) analytical solution for surface displacement from a rectangular fault.

Includes Wells & Coppersmith (1994) scaling laws for deriving fault geometry
from earthquake magnitude.
"""

from dataclasses import dataclass
import numpy as np
from tsunami.simulation.grid import Grid, METERS_PER_DEG_LAT


@dataclass
class FaultParams:
    lat: float
    lon: float
    strike: float
    dip: float
    rake: float
    slip_m: float
    length_km: float
    width_km: float
    depth_km: float


def magnitude_to_fault_params(lat, lon, magnitude, direction):
    log_length = -2.86 + 0.63 * magnitude
    log_width = -1.61 + 0.41 * magnitude
    log_slip = -4.80 + 0.69 * magnitude
    length_km = 10**log_length
    width_km = 10**log_width
    slip_m = 10**log_slip
    dip = 15.0
    rake = 90.0
    depth_km = 10.0
    return FaultParams(
        lat=lat, lon=lon, strike=direction, dip=dip, rake=rake,
        slip_m=slip_m, length_km=length_km, width_km=width_km, depth_km=depth_km,
    )


def compute_displacement(params, grid):
    if params.slip_m == 0.0:
        return np.zeros(grid.depth.shape)

    cos_lat = np.cos(np.radians(params.lat))
    meters_per_deg_lon = METERS_PER_DEG_LAT * cos_lat

    lon_2d, lat_2d = np.meshgrid(grid.lon, grid.lat)
    x = (lon_2d - params.lon) * meters_per_deg_lon
    y = (lat_2d - params.lat) * METERS_PER_DEG_LAT

    strike_rad = np.radians(params.strike)
    cos_s = np.cos(strike_rad)
    sin_s = np.sin(strike_rad)
    xp = x * sin_s + y * cos_s
    yp = -x * cos_s + y * sin_s

    length = params.length_km * 1000.0
    width = params.width_km * 1000.0
    depth = params.depth_km * 1000.0

    dip_rad = np.radians(params.dip)
    rake_rad = np.radians(params.rake)

    U1 = params.slip_m * np.cos(rake_rad)
    U2 = params.slip_m * np.sin(rake_rad)

    cos_d = np.cos(dip_rad)
    sin_d = np.sin(dip_rad)

    uz = np.zeros_like(xp)

    for sign_xi, xi_val in [(-1, -length / 2), (1, length / 2)]:
        for sign_eta, eta_val in [(-1, 0.0), (1, width)]:
            xi = xp - xi_val
            eta = yp * cos_d + (depth + eta_val * sin_d) * sin_d - eta_val * cos_d
            q = yp * sin_d - (depth + eta_val * sin_d) * cos_d

            R = np.sqrt(xi**2 + eta**2 + q**2)
            R = np.maximum(R, 1e-10)

            sign = sign_xi * sign_eta

            if abs(U1) > 1e-15:
                uz += sign * U1 / (2 * np.pi) * _uz_ss(xi, eta, q, R, dip_rad)
            if abs(U2) > 1e-15:
                uz += sign * U2 / (2 * np.pi) * _uz_ds(xi, eta, q, R, dip_rad)

    return uz


def _uz_ss(xi, eta, q, R, dip):
    sin_d = np.sin(dip)
    cos_d = np.cos(dip)
    d_tilde = eta * sin_d - q * cos_d
    R_eta = R + eta
    R_eta = np.where(np.abs(R_eta) < 1e-10, 1e-10, R_eta)
    return (
        d_tilde * q / (R * (R + eta))
        + q * sin_d / (R + eta)
        + np.arctan2(xi * eta, q * R)
    ) * (-1)


def _uz_ds(xi, eta, q, R, dip):
    sin_d = np.sin(dip)
    cos_d = np.cos(dip)
    d_tilde = eta * sin_d - q * cos_d
    y_tilde = eta * cos_d + q * sin_d
    R_eta = R + eta
    R_eta = np.where(np.abs(R_eta) < 1e-10, 1e-10, R_eta)
    R_xi = R + xi
    R_xi = np.where(np.abs(R_xi) < 1e-10, 1e-10, R_xi)
    return (
        d_tilde * q / (R * (R + xi))
        + sin_d * np.arctan2(xi * eta, q * R)
        - (y_tilde * q) / (R * (R + xi))
    )
