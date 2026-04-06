"""Extended Boussinesq equations solver for fine-scale nearshore modeling.

Adds dispersive correction terms to the Shallow Water Equations,
producing more accurate wave shapes in shallow water where wavelength
and depth are comparable.

The Boussinesq system:
    deta/dt + div((h+eta)u) = 0
    du/dt + (u.grad)u + g*grad(eta) = B*h^2*d^2(du/dt)/dx^2 + dispersive terms

where B = 1/15 (Peregrine's Boussinesq approximation).

Uses SWE as the base solver with dispersive corrections applied via
operator splitting.
"""

from dataclasses import dataclass
from typing import Callable
import numpy as np
from scipy.interpolate import RegularGridInterpolator

from tsunami.simulation.grid import Grid
from tsunami.simulation.swe_solver import (
    SWEState,
    create_initial_state,
    compute_cfl_dt,
    swe_step,
    G,
    MIN_DEPTH,
)


@dataclass
class BoussinesqConfig:
    duration_seconds: float
    output_interval_seconds: float = 60.0
    cfl: float = 0.3
    dispersion_coefficient: float = 1.0 / 15.0  # Peregrine B coefficient


@dataclass
class BoundaryConditions:
    """Time-varying boundary conditions from coarse SWE solution."""

    time_seconds: list[float]
    eta_north: list[np.ndarray]
    eta_south: list[np.ndarray]
    eta_east: list[np.ndarray]
    eta_west: list[np.ndarray]

    @property
    def n_timesteps(self) -> int:
        return len(self.time_seconds)


@dataclass
class BoussinesqResult:
    max_wave_heights: np.ndarray  # (ny, nx) max |eta|
    max_velocity: np.ndarray  # (ny, nx) max |velocity|
    frames: list[tuple[float, np.ndarray]]  # [(time_s, eta), ...]


def create_boundary_conditions_from_swe(
    coarse_grid: Grid,
    fine_grid: Grid,
    coarse_states: list[tuple[float, SWEState]],
) -> BoundaryConditions:
    """Extract boundary conditions for the fine grid from coarse SWE states."""
    times = []
    eta_n, eta_s, eta_e, eta_w = [], [], [], []

    for t, state in coarse_states:
        times.append(t)
        interp = RegularGridInterpolator(
            (coarse_grid.lat, coarse_grid.lon),
            state.eta,
            method="linear",
            bounds_error=False,
            fill_value=0.0,
        )

        north_pts = np.column_stack([
            np.full(len(fine_grid.lon), fine_grid.lat[-1]),
            fine_grid.lon,
        ])
        eta_n.append(interp(north_pts))

        south_pts = np.column_stack([
            np.full(len(fine_grid.lon), fine_grid.lat[0]),
            fine_grid.lon,
        ])
        eta_s.append(interp(south_pts))

        east_pts = np.column_stack([
            fine_grid.lat,
            np.full(len(fine_grid.lat), fine_grid.lon[-1]),
        ])
        eta_e.append(interp(east_pts))

        west_pts = np.column_stack([
            fine_grid.lat,
            np.full(len(fine_grid.lat), fine_grid.lon[0]),
        ])
        eta_w.append(interp(west_pts))

    return BoundaryConditions(
        time_seconds=times,
        eta_north=eta_n, eta_south=eta_s,
        eta_east=eta_e, eta_west=eta_w,
    )


def _apply_dispersive_correction(
    state: SWEState, grid: Grid, dt: float, B: float,
) -> SWEState:
    """Apply Boussinesq dispersive correction via Laplacian of momentum."""
    dx, dy = grid.cell_size_m()
    if dx == 0 or dy == 0:
        return state

    h = grid.depth
    h2 = h**2

    # Laplacian of hu
    lap_hu = np.zeros_like(state.hu)
    lap_hu[1:-1, 1:-1] = (
        (state.hu[1:-1, 2:] - 2 * state.hu[1:-1, 1:-1] + state.hu[1:-1, :-2]) / dx**2
        + (state.hu[2:, 1:-1] - 2 * state.hu[1:-1, 1:-1] + state.hu[:-2, 1:-1]) / dy**2
    )

    # Laplacian of hv
    lap_hv = np.zeros_like(state.hv)
    lap_hv[1:-1, 1:-1] = (
        (state.hv[1:-1, 2:] - 2 * state.hv[1:-1, 1:-1] + state.hv[1:-1, :-2]) / dx**2
        + (state.hv[2:, 1:-1] - 2 * state.hv[1:-1, 1:-1] + state.hv[:-2, 1:-1]) / dy**2
    )

    # Apply correction with stability limiting
    correction_hu = B * h2 * lap_hu * dt
    correction_hv = B * h2 * lap_hv * dt

    max_corr = 0.1 * np.maximum(np.abs(state.hu), 0.01)
    correction_hu = np.clip(correction_hu, -max_corr, max_corr)
    max_corr = 0.1 * np.maximum(np.abs(state.hv), 0.01)
    correction_hv = np.clip(correction_hv, -max_corr, max_corr)

    return SWEState(
        eta=state.eta,
        hu=state.hu + correction_hu,
        hv=state.hv + correction_hv,
    )


def _apply_boundary_conditions(
    state: SWEState,
    bc: BoundaryConditions,
    t: float,
) -> SWEState:
    """Apply time-interpolated boundary conditions to the state."""
    times = bc.time_seconds
    if t <= times[0]:
        idx = 0
        frac = 0.0
    elif t >= times[-1]:
        idx = len(times) - 2
        frac = 1.0
    else:
        idx = 0
        for i in range(len(times) - 1):
            if times[i] <= t <= times[i + 1]:
                idx = i
                frac = (t - times[i]) / (times[i + 1] - times[i])
                break

    def lerp(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return a * (1 - frac) + b * frac

    idx2 = min(idx + 1, len(times) - 1)
    eta = state.eta.copy()
    eta[-1, :] = lerp(bc.eta_north[idx], bc.eta_north[idx2])
    eta[0, :] = lerp(bc.eta_south[idx], bc.eta_south[idx2])
    eta[:, -1] = lerp(bc.eta_east[idx], bc.eta_east[idx2])
    eta[:, 0] = lerp(bc.eta_west[idx], bc.eta_west[idx2])

    return SWEState(eta=eta, hu=state.hu, hv=state.hv)


def run_boussinesq(
    grid: Grid,
    initial_eta: np.ndarray,
    config: BoussinesqConfig,
    boundary_conditions: BoundaryConditions | None = None,
    progress_callback: Callable[[float], None] | None = None,
) -> BoussinesqResult:
    """Run the Boussinesq solver using operator splitting: SWE step + dispersive correction."""
    state = create_initial_state(grid, initial_eta)

    dx, dy = grid.cell_size_m()
    max_depth = float(np.max(grid.depth))
    if max_depth <= 0:
        return BoussinesqResult(
            max_wave_heights=np.zeros(grid.depth.shape),
            max_velocity=np.zeros(grid.depth.shape),
            frames=[],
        )

    dt = compute_cfl_dt(dx, dy, max_depth, config.cfl)

    max_heights = np.zeros(grid.depth.shape)
    max_velocity = np.zeros(grid.depth.shape)
    frames: list[tuple[float, np.ndarray]] = []

    t = 0.0
    next_output = config.output_interval_seconds
    total_steps = int(config.duration_seconds / dt) if dt > 0 else 0
    step = 0

    while t < config.duration_seconds:
        step_dt = min(dt, config.duration_seconds - t)

        # 1. SWE step
        state = swe_step(state, grid, step_dt)

        # 2. Dispersive correction
        state = _apply_dispersive_correction(
            state, grid, step_dt, config.dispersion_coefficient,
        )

        # 3. Apply boundary conditions if provided
        if boundary_conditions is not None:
            state = _apply_boundary_conditions(state, boundary_conditions, t)

        t += step_dt
        step += 1

        # Track maxima
        np.maximum(max_heights, np.abs(state.eta), out=max_heights)
        H = np.maximum(grid.depth + state.eta, MIN_DEPTH)
        speed = np.sqrt((state.hu / H) ** 2 + (state.hv / H) ** 2)
        np.maximum(max_velocity, speed, out=max_velocity)

        # Output frame
        if t >= next_output:
            frames.append((t, state.eta.copy()))
            next_output += config.output_interval_seconds

        # Progress
        if progress_callback and total_steps > 0 and step % max(total_steps // 20, 1) == 0:
            progress_callback(min(100.0, 100.0 * t / config.duration_seconds))

    if progress_callback:
        progress_callback(100.0)

    return BoussinesqResult(
        max_wave_heights=max_heights,
        max_velocity=max_velocity,
        frames=frames,
    )
