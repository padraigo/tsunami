# Tsunami Wave Solver — Technical Reference

This document describes the numerical methods, equations, and implementation details of the tsunami simulation engine. Source files referenced:

- `backend/src/tsunami/simulation/swe_solver.py` — Shallow Water Equations solver
- `backend/src/tsunami/simulation/boussinesq.py` — Boussinesq dispersive solver
- `backend/src/tsunami/simulation/tides.py` — Harmonic tidal model
- `backend/src/tsunami/api/run.py` — Two-level nesting pipeline

---

## 1. Shallow Water Equations

The solver integrates the 2D nonlinear shallow water equations (SWE) in **conservation form**:

$$\frac{\partial \eta}{\partial t} + \frac{\partial (hu)}{\partial x} + \frac{\partial (hv)}{\partial y} = 0$$

$$\frac{\partial (hu)}{\partial t} + \frac{\partial \left(hu^2 + \tfrac{1}{2}g H^2\right)}{\partial x} + \frac{\partial (huv)}{\partial y} = -gH\frac{\partial b}{\partial x}$$

$$\frac{\partial (hv)}{\partial t} + \frac{\partial (huv)}{\partial x} + \frac{\partial \left(hv^2 + \tfrac{1}{2}g H^2\right)}{\partial y} = -gH\frac{\partial b}{\partial y}$$

### Variable Definitions

| Symbol | Code name | Units | Description |
|--------|-----------|-------|-------------|
| $\eta$ | `eta` | m | Free-surface elevation above mean sea level |
| $h$ | `grid.depth` | m | Still-water depth (from bathymetry, positive in ocean) |
| $H$ | `H` | m | Total water column depth: $H = h + \eta$ |
| $u$ | `u` | m/s | Depth-averaged velocity in x (longitude) direction |
| $v$ | `v` | m/s | Depth-averaged velocity in y (latitude) direction |
| $hu$ | `hu` | m²/s | x-momentum (conserved variable) |
| $hv$ | `hv` | m²/s | y-momentum (conserved variable) |
| $b$ | — | m | Bathymetry elevation (negative of depth) |

### Physical Constants

```python
G = 9.81          # gravitational acceleration (m/s²)
MIN_DEPTH = 0.01  # wet/dry threshold (m)
```

The conserved state is stored in `SWEState(eta, hu, hv)`. Velocities are recovered as:

```python
H = h + eta
H = np.maximum(H, 0.0)
wet = H > MIN_DEPTH
u = np.where(wet, hu / H, 0.0)
v = np.where(wet, hv / H, 0.0)
```

---

## 2. Lax-Friedrichs Finite Volume Scheme

### `_lf_flux_divergence` (lines 136–157)

The Lax-Friedrichs numerical flux at a cell interface is:

$$F_{i+1/2} = \frac{1}{2}\left(F_i + F_{i+1}\right) - \frac{\alpha}{2}\left(U_{i+1} - U_i\right)$$

where $\alpha$ is the numerical dissipation coefficient. The flux divergence across cell $i$ is:

$$\frac{\Delta F}{\Delta x} = \frac{F_{i+1/2} - F_{i-1/2}}{\Delta x}$$

In code, the right and left interface fluxes are:

```python
flux_right = 0.5 * (flux + f_plus)  - 0.5 * alpha * (u_plus - conserved)
flux_left  = 0.5 * (f_minus + flux) - 0.5 * alpha * (conserved - u_minus)
divergence = flux_right - flux_left
```

Wall interface fluxes are zeroed out for reflective boundary conditions:

```python
if axis == 0:
    flux_right[-1, :] = 0.0  # top wall
    flux_left[0, :]   = 0.0  # bottom wall
else:
    flux_right[:, -1] = 0.0  # right wall
    flux_left[:, 0]   = 0.0  # left wall
```

This telescoping structure ensures exact conservation of the domain integral.

### `swe_step` — Full Update (lines 49–133)

Each call advances the state by one timestep `dt`. The update sequence is:

1. **Compute total depth and velocity** (wet/dry detection).
2. **Compute perturbation pressure** (see Section 3).
3. **Assemble fluxes** in both dimensions.
4. **Compute flux divergences** using `_lf_flux_divergence`.
5. **Compute bathymetry source terms**.
6. **Forward Euler update**: $U^{n+1} = U^n - \Delta t \, (\delta F_x + \delta F_y) + \Delta t \, S$
7. **Apply reflective BCs**: zero normal momentum on all four walls.
8. **Dry cell treatment**: zero momentum where $H \le$ `MIN_DEPTH`.
9. **Stability guards** (Section 5).

### CFL Timestep

The timestep is set globally from the fastest gravity wave speed:

$$\Delta t = \text{CFL} \cdot \frac{\min(\Delta x, \Delta y)}{\sqrt{g \cdot h_{\max}}}$$

```python
def compute_cfl_dt(dx, dy, max_depth, cfl=0.4):
    c = np.sqrt(G * max_depth)
    ds = min(abs(dx), abs(dy))
    return cfl * ds / c
```

Default `cfl = 0.4`. The Boussinesq solver uses a tighter `cfl = 0.3` due to the additional dispersive correction.

---

## 3. Well-Balanced Formulation

### Perturbation Pressure

Instead of including the full hydrostatic pressure $\tfrac{1}{2}g H^2$ in the x-momentum flux, the implementation uses a **perturbation pressure**:

$$p_{\text{pert}} = \tfrac{1}{2} g (H^2 - h^2) = g h \eta + \tfrac{1}{2} g \eta^2$$

```python
pressure_pert = 0.5 * G * (H**2 - h**2)
```

This avoids large-magnitude floating-point cancellation that would occur when subtracting the dominant hydrostatic background $\tfrac{1}{2}g h^2$ from the total flux. Since $\eta \ll h$ in the open ocean, $p_{\text{pert}}$ is many orders of magnitude smaller than $\tfrac{1}{2}g H^2$, retaining more significant digits in the flux computation.

### Source Term

Using the perturbation pressure in the flux, the remaining bathymetry source term is:

$$S_{hu} = g \eta \frac{\partial h}{\partial x}, \qquad S_{hv} = g \eta \frac{\partial h}{\partial y}$$

```python
dhdx[:, 1:-1] = (h[:, 2:] - h[:, :-2]) / (2 * dx)   # central difference
dhdy[1:-1, :] = (h[2:, :] - h[:-2, :]) / (2 * dy)

src_hu = G * eta * dhdx
src_hv = G * eta * dhdy
```

**Flat bathymetry property**: when $h$ is constant, $\partial h / \partial x = \partial h / \partial y = 0$, so the source is identically zero. The scheme is therefore exactly well-balanced for lake-at-rest initial conditions ($\eta = 0$, $hu = hv = 0$).

---

## 4. 2D Stability Fix — Alpha Halving

### The Problem

In a standard unsplit 2D Lax-Friedrichs scheme, each dimension uses $\alpha = \Delta x / \Delta t$. The center cell coefficient in the update equation is:

$$1 - \underbrace{\frac{1}{2}}_{\text{x-dim}} - \underbrace{\frac{1}{2}}_{\text{y-dim}} = 0$$

A center coefficient of zero means information from the current cell does not contribute to the next timestep. This is marginally stable at best, and in practice leads to checkerboard instabilities.

### The Fix

The implementation uses $\alpha = \tfrac{1}{2} \cdot \Delta x / \Delta t$ for each dimension independently:

```python
alpha_x = 0.5 * dx / dt
alpha_y = 0.5 * dy / dt
```

This gives a center coefficient of:

$$1 - \underbrace{\frac{1}{4}}_{\text{x-dim}} - \underbrace{\frac{1}{4}}_{\text{y-dim}} = 0.5$$

The center coefficient $0.5 > 0$ ensures the scheme is genuinely dissipative. This is equivalent to halving the LF numerical viscosity per dimension in the unsplit 2D setting, as documented in the code comment at line 77:

> "Factor of 0.5 for unsplit 2D: each dimension contributes half the LF dissipation so the total center coefficient stays positive (0.5)."

---

## 5. Stability Guards

Three layers of numerical protection are applied at the end of each `swe_step` call (lines 120–131).

### Eta Clamp

```python
max_ocean_depth = max(float(np.max(grid.depth)), 1.0)
max_eta = min(100.0, max_ocean_depth * 0.1)
new_eta = np.clip(new_eta, -max_eta, max_eta)
```

The maximum allowed surface elevation is capped at the smaller of 100 m or 10% of the maximum ocean depth. Rationale: even extreme open-ocean tsunamis do not exceed ~50 m amplitude; the 100 m hard ceiling prevents runaway values while allowing physical extremes.

### Momentum Clamp

```python
max_mom = max_eta * np.sqrt(G * max_ocean_depth)
new_hu = np.clip(new_hu, -max_mom, max_mom)
new_hv = np.clip(new_hv, -max_mom, max_mom)
```

Momentum is clipped to the product of the maximum allowed elevation and the shallow-water wave speed $\sqrt{g h_{\max}}$, giving a consistent physical bound.

### NaN/Inf Kill

```python
new_eta = np.nan_to_num(new_eta, nan=0.0, posinf=0.0, neginf=0.0)
new_hu  = np.nan_to_num(new_hu,  nan=0.0, posinf=0.0, neginf=0.0)
new_hv  = np.nan_to_num(new_hv,  nan=0.0, posinf=0.0, neginf=0.0)
```

Any floating-point fault (NaN or Inf) is replaced with zero. This handles edge cases that arise from sharp bathymetry gradients in raw GEBCO data, where a single problematic cell would otherwise corrupt the entire domain.

---

## 6. Bathymetry Processing

### GEBCO 2025 Loading

Bathymetry is loaded from GEBCO 2025 NetCDF files via `BathymetryService.get_bathymetry(grid, source="auto")`. The raw elevation data (positive = land, negative = ocean) is negated to yield depth (positive in ocean). Lat/lon subsetting and antimeridian wrapping for Pacific domains (lon > 180°) are handled by the `Grid` module.

### Inland Water Masking — `_mask_inland_water` (lines 35–66, `run.py`)

Inland lakes and rivers are hydrologically disconnected from the open ocean and should not participate in wave propagation. The mask is computed by connected-component flood-fill:

```python
from scipy.ndimage import label
labeled, n_features = label(wet)          # connected components of wet cells
edge_labels = set()
edge_labels.update(labeled[0, :].tolist())   # top edge
edge_labels.update(labeled[-1, :].tolist())  # bottom edge
edge_labels.update(labeled[:, 0].tolist())   # left edge
edge_labels.update(labeled[:, -1].tolist())  # right edge
edge_labels.discard(0)                       # 0 = dry land
```

Any wet component that does not touch the domain boundary is reclassified as land at $+10$ m elevation:

```python
result[labeled == lbl] = -10.0  # depth = -10m => 10m above sea level
```

### Bathymetry Smoothing

After masking, a gentle uniform filter is applied to reduce abrupt depth transitions:

```python
from scipy.ndimage import uniform_filter
depth = uniform_filter(depth, size=2, mode='nearest')
```

A filter size of 2 cells averages over a $2 \times 2$ neighbourhood, smoothing single-cell spikes that would otherwise generate excessive source term gradients.

---

## 7. Boussinesq Solver (Fine-Scale)

The Boussinesq solver extends the SWE by adding frequency-dispersion corrections, producing more accurate wave shapes in regions where the wavelength is comparable to the water depth (nearshore and shelf environments).

### Governing Equations

The Peregrine (1967) Boussinesq system adds dispersive terms to the momentum equations:

$$\frac{\partial (hu)}{\partial t} + \cdots = B h^2 \nabla^2 \frac{\partial (hu)}{\partial t}$$

where $B = 1/15$ is the Peregrine dispersion coefficient (`dispersion_coefficient = 1.0 / 15.0`).

### Operator Splitting

Each time step applies two operators in sequence (`run_boussinesq`, lines 218–232):

1. **SWE step**: `state = swe_step(state, grid, step_dt)` — advances all conserved variables.
2. **Dispersive correction**: `state = _apply_dispersive_correction(state, grid, step_dt, B)` — adds $B h^2 \nabla^2(hu)$ to the momentum.

### Dispersive Correction — `_apply_dispersive_correction` (lines 113–151)

The discrete Laplacian of x-momentum is computed with the standard five-point stencil:

$$\nabla^2 (hu)_{i,j} = \frac{(hu)_{i,j+1} - 2(hu)_{i,j} + (hu)_{i,j-1}}{\Delta x^2} + \frac{(hu)_{i+1,j} - 2(hu)_{i,j} + (hu)_{i-1,j}}{\Delta y^2}$$

```python
lap_hu[1:-1, 1:-1] = (
    (state.hu[1:-1, 2:] - 2*state.hu[1:-1, 1:-1] + state.hu[1:-1, :-2]) / dx**2
  + (state.hu[2:, 1:-1] - 2*state.hu[1:-1, 1:-1] + state.hu[:-2, 1:-1]) / dy**2
)
```

The correction is applied with stability limiting to prevent the dispersive term from dominating:

```python
correction_hu = B * h2 * lap_hu * dt
max_corr = 0.1 * np.maximum(np.abs(state.hu), 0.01)
correction_hu = np.clip(correction_hu, -max_corr, max_corr)
```

The correction is clipped to 10% of the current momentum magnitude at each cell, ensuring the dispersive operator never reverses the flow direction in a single step.

### Boundary Conditions from Coarse SWE

Fine-grid boundaries are driven by the coarse SWE solution. `create_boundary_conditions_from_swe` (lines 63–110) uses `scipy.interpolate.RegularGridInterpolator` to spatially interpolate the coarse $\eta$ field onto the four edges of the fine grid at each output timestep:

```python
interp = RegularGridInterpolator(
    (coarse_grid.lat, coarse_grid.lon),
    state.eta,
    method="linear",
    bounds_error=False,
    fill_value=0.0,
)
```

During the fine-grid run, `_apply_boundary_conditions` linearly interpolates in time between the stored coarse frames and overwrites the outermost row/column of `eta` at each substep.

---

## 8. Two-Level Nesting Pipeline

The full simulation (`run.py`, `run_coarse` endpoint) operates in two tiers.

### Tier 1 — Coarse SWE

1. **Grid creation**: `domain_for_magnitude` sizes the domain to the earthquake magnitude; `create_grid` builds a regular lat/lon grid at the user-specified resolution (e.g., 20 km).
2. **Bathymetry**: GEBCO depth loaded, inland water masked, smoothed.
3. **Source**: Okada (1985) fault displacement computed via `compute_displacement`. If an earthquake datetime is provided, the equilibrium tide field is added:
   ```python
   tide_offset = compute_tide_field(grid.lat, grid.lon, sim.earthquake_datetime)
   displacement = displacement + tide_offset
   ```
4. **SWE run**: `run_swe` integrates forward for `duration_hours * 3600` seconds at `cfl=0.4`. A `frame_callback` captures `SWEState` snapshots every `output_interval_seconds`.
5. **Full-resolution frame save** (`_save_coarse_frames`, lines 118–133): all frames are saved to `coarse_frames.npz` (compressed NumPy archive) for later BC extraction.

### Impact Detection and Focus Zone Selection

After the coarse run:

```python
impacts = detect_coastal_impacts(grid, max_heights, depth_threshold=300.0, height_threshold=0.1)
zones   = suggest_focus_zones(impacts, cluster_radius_km=200.0)
```

- **Coastal cells** are defined as wet cells with $h < 300$ m.
- **Impact** requires $|\eta|_{\max} > 0.1$ m at a coastal cell.
- **Clustering**: greedy, absorbing all impact points within 200 km radius into the same focus zone.
- The top 3 zones by maximum impact height are promoted to detail runs.

### Tier 2 — Detail Boussinesq (`_run_detail_zone`, lines 148–195)

For each focus zone:

1. **Fine grid**: built at 5 km resolution over the zone bounds.
2. **High-resolution bathymetry**: fetched for the fine grid, masked, smoothed.
3. **BC extraction**: `create_boundary_conditions_from_swe` interpolates all coarse frames to the fine grid boundaries.
4. **Boussinesq run**: `run_boussinesq` with `cfl=0.3`, duration capped at 1800 s (30 minutes).
5. **Inundation**: `compute_inundation` maps flood depth = max wave height minus land elevation.

Results include `max_runup_m`, `max_wave_height`, and an inundation GeoJSON polygon.

---

## 9. Tidal Model

The tidal model (`tides.py`) computes instantaneous tide heights across a lat/lon grid using four dominant harmonic constituents.

### Constituents

| Name | Period (h) | Equilibrium amplitude (m) | Type | Angular frequency $\omega$ |
|------|-----------|--------------------------|------|---------------------------|
| M2 | 12.4206 | 0.24 | Semidiurnal | $2\pi / 12.4206$ rad/h |
| S2 | 12.0000 | 0.11 | Semidiurnal | $2\pi / 12.0$ rad/h |
| K1 | 23.9345 | 0.14 | Diurnal | $2\pi / 23.9345$ rad/h |
| O1 | 25.8193 | 0.10 | Diurnal | $2\pi / 25.8193$ rad/h |

### Astronomical Arguments (Meeus)

The astronomical argument (phase origin $V_0$) for each constituent is derived from Julian centuries $T$ elapsed since J2000.0 (`_astronomical_arguments`, lines 31–41):

$$s = (218.3165 + 481267.8813 \cdot T) \bmod 360 \quad \text{(Moon's mean longitude)}$$
$$h_\odot = (280.4661 + 36000.7698 \cdot T) \bmod 360 \quad \text{(Sun's mean longitude)}$$

Phase origins (`_constituent_phase`, lines 44–55):

| Constituent | $V_0$ (degrees) |
|-------------|----------------|
| M2 | $(2 h_\odot - 2s) \bmod 360$ |
| S2 | $0$ |
| K1 | $(h_\odot + 90) \bmod 360$ |
| O1 | $(h_\odot - 2s - 90) \bmod 360$ |

### Equilibrium Tide Spatial Patterns

The equilibrium tide amplitude varies with latitude according to the constituent type (`compute_tide_field`, lines 58–97):

**Semidiurnal** (M2, S2): spatial pattern $\propto \cos^2(\phi)$, longitude-dependent phase $2\lambda$:

$$\eta_{\text{semi}}(\phi, \lambda, t) = A \cos^2(\phi) \cdot \cos\!\left(V_0 + \omega t + 2\lambda\right)$$

**Diurnal** (K1, O1): spatial pattern $\propto \sin(2\phi)$, longitude-dependent phase $\lambda$:

$$\eta_{\text{diurnal}}(\phi, \lambda, t) = A \sin(2\phi) \cdot \cos\!\left(V_0 + \omega t + \lambda\right)$$

where $\phi$ is latitude in radians, $\lambda$ is longitude in radians, $t$ is the time of day in hours, and $A$ is the equilibrium amplitude from the table above.

The total tide height is the sum over all four constituents:

$$\eta_{\text{tide}}(\phi, \lambda, t) = \sum_{\text{const}} \eta_{\text{const}}(\phi, \lambda, t)$$

### Usage in the Pipeline

When an earthquake datetime is provided, the tide field is added to the Okada seafloor displacement before the SWE initial condition is set:

```python
tide_offset = compute_tide_field(grid.lat, grid.lon, sim.earthquake_datetime)
tide_offset  = np.where(grid.depth > 0, tide_offset, 0.0)   # ocean cells only
displacement = displacement + tide_offset
```

This approximates the sea-surface offset due to the background tidal state at the moment of rupture.

---

## Key Equations Summary

| Quantity | Expression |
|----------|-----------|
| Total depth | $H = h + \eta$, clamped to $H \ge 0$ |
| Wave speed | $c = \sqrt{g H}$ |
| CFL timestep | $\Delta t = \text{CFL} \cdot \min(\Delta x, \Delta y) / \sqrt{g h_{\max}}$ |
| Perturbation pressure | $p_{\text{pert}} = \tfrac{1}{2} g (H^2 - h^2)$ |
| Bathymetry source | $S_{hu} = g \eta \, \partial h / \partial x$ |
| LF dissipation (2D) | $\alpha_{x} = \tfrac{1}{2} \Delta x / \Delta t$ |
| Boussinesq correction | $\delta(hu) = B h^2 \nabla^2(hu) \cdot \Delta t$, $B = 1/15$ |
| Eta stability bound | $|\eta| \le \min(100, 0.1 \cdot h_{\max})$ |
| Momentum bound | $|hu| \le |\eta|_{\max} \cdot \sqrt{g h_{\max}}$ |
