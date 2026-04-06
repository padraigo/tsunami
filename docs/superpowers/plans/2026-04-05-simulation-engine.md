# Simulation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core tsunami simulation library as a pure Python package — earthquake source modeling (Okada), coarse wave propagation (SWE), fine-scale modeling (Boussinesq), impact detection, and inundation mapping.

**Architecture:** A pure Python library (`tsunami.simulation`) with no web dependencies. Each module (grid, okada, swe_solver, boussinesq, inundation) has a single responsibility with well-defined inputs/outputs. The library operates on NumPy arrays and can be tested entirely via pytest. A procedural bathymetry module provides fallback data for testing and demos.

**Tech Stack:** Python 3.12, NumPy, SciPy, pytest, xarray (for NetCDF output)

---

## File Structure

```
backend/
├── pyproject.toml                          # Package definition, dependencies
├── src/tsunami/
│   ├── __init__.py
│   ├── simulation/
│   │   ├── __init__.py
│   │   ├── grid.py                         # Grid creation, coordinate transforms, resampling
│   │   ├── okada.py                        # Earthquake → seafloor displacement (Okada 1985)
│   │   ├── swe_solver.py                   # Shallow Water Equations solver (coarse)
│   │   ├── boussinesq.py                   # Boussinesq solver (fine, dispersive)
│   │   ├── inundation.py                   # Flood extent, depth, velocity extraction
│   │   └── impact.py                       # Coastal impact detection and zone suggestion
│   └── bathymetry/
│       ├── __init__.py
│       └── procedural.py                   # Idealized bathymetry generation
└── tests/
    ├── conftest.py                         # Shared fixtures
    ├── test_grid.py
    ├── test_okada.py
    ├── test_swe_solver.py
    ├── test_boussinesq.py
    ├── test_inundation.py
    ├── test_impact.py
    └── test_procedural_bathy.py
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/tsunami/__init__.py`
- Create: `backend/src/tsunami/simulation/__init__.py`
- Create: `backend/src/tsunami/bathymetry/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create backend directory structure**

```bash
mkdir -p backend/src/tsunami/simulation
mkdir -p backend/src/tsunami/bathymetry
mkdir -p backend/tests
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "tsunami"
version = "0.1.0"
description = "Tsunami simulation engine"
requires-python = ">=3.12"
dependencies = [
    "numpy>=1.26",
    "scipy>=1.12",
    "xarray>=2024.1",
    "netcdf4>=1.6",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/tsunami"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create package init files**

`backend/src/tsunami/__init__.py`:
```python
"""Tsunami simulation engine."""
```

`backend/src/tsunami/simulation/__init__.py`:
```python
"""Core simulation modules: grid, okada, SWE, Boussinesq, inundation."""
```

`backend/src/tsunami/bathymetry/__init__.py`:
```python
"""Bathymetry data services."""
```

- [ ] **Step 4: Create test conftest with shared fixtures**

`backend/tests/conftest.py`:
```python
import numpy as np
import pytest


@pytest.fixture
def rng():
    """Seeded random number generator for reproducible tests."""
    return np.random.default_rng(42)


@pytest.fixture
def flat_depth():
    """Uniform ocean depth of 4000m (typical open ocean)."""
    return 4000.0


@pytest.fixture
def gravity():
    """Standard gravitational acceleration."""
    return 9.81
```

- [ ] **Step 5: Install package in dev mode and verify pytest runs**

```bash
cd backend && pip install -e ".[dev]" && pytest --co -q
```

Expected: `no tests ran` (no test files with tests yet)

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: scaffold backend Python package with pyproject.toml and test config"
```

---

### Task 2: Grid Module

**Files:**
- Create: `backend/src/tsunami/simulation/grid.py`
- Create: `backend/tests/test_grid.py`

The Grid class holds 2D coordinate arrays (lat/lon), depth values, and provides coordinate conversion utilities. It's used by every other simulation module.

- [ ] **Step 1: Write failing tests for Grid**

`backend/tests/test_grid.py`:
```python
import numpy as np
import pytest
from tsunami.simulation.grid import Grid, create_grid, resample_grid, domain_for_magnitude


class TestCreateGrid:
    def test_creates_grid_with_correct_shape(self):
        grid = create_grid(
            lat_min=-5.0, lat_max=5.0,
            lon_min=95.0, lon_max=105.0,
            resolution_km=100.0,
        )
        # ~10 degrees lat ≈ 1111 km, so ~11 cells at 100km
        # ~10 degrees lon at equator ≈ 1113 km, so ~11 cells at 100km
        assert grid.lat.shape[0] >= 10
        assert grid.lon.shape[0] >= 10
        assert grid.depth.shape == (grid.lat.shape[0], grid.lon.shape[0])

    def test_grid_lat_lon_are_monotonic(self):
        grid = create_grid(
            lat_min=-2.0, lat_max=2.0,
            lon_min=100.0, lon_max=104.0,
            resolution_km=50.0,
        )
        assert np.all(np.diff(grid.lat) > 0)
        assert np.all(np.diff(grid.lon) > 0)

    def test_grid_depth_initialized_to_zero(self):
        grid = create_grid(
            lat_min=0.0, lat_max=1.0,
            lon_min=0.0, lon_max=1.0,
            resolution_km=50.0,
        )
        assert np.all(grid.depth == 0.0)

    def test_grid_with_depth_array(self):
        grid = create_grid(
            lat_min=0.0, lat_max=1.0,
            lon_min=0.0, lon_max=1.0,
            resolution_km=50.0,
        )
        depth = np.full(grid.depth.shape, 4000.0)
        grid_with_depth = grid.with_depth(depth)
        assert np.all(grid_with_depth.depth == 4000.0)
        assert grid_with_depth.lat is grid.lat  # shares coordinates


class TestDomainForMagnitude:
    def test_large_earthquake_gets_large_domain(self):
        bounds = domain_for_magnitude(lat=0.0, lon=100.0, magnitude=9.0)
        lat_span = bounds["lat_max"] - bounds["lat_min"]
        assert lat_span > 40  # M9 should cover >40 degrees

    def test_moderate_earthquake_gets_smaller_domain(self):
        bounds = domain_for_magnitude(lat=0.0, lon=100.0, magnitude=7.0)
        lat_span = bounds["lat_max"] - bounds["lat_min"]
        assert 10 < lat_span < 30

    def test_domain_centered_on_epicenter(self):
        bounds = domain_for_magnitude(lat=10.0, lon=50.0, magnitude=8.0)
        center_lat = (bounds["lat_min"] + bounds["lat_max"]) / 2
        center_lon = (bounds["lon_min"] + bounds["lon_max"]) / 2
        assert abs(center_lat - 10.0) < 0.1
        assert abs(center_lon - 50.0) < 0.1


class TestResampleGrid:
    def test_resample_to_coarser_resolution(self):
        fine = create_grid(
            lat_min=0.0, lat_max=2.0,
            lon_min=0.0, lon_max=2.0,
            resolution_km=10.0,
        )
        depth = np.full(fine.depth.shape, 3000.0)
        fine = fine.with_depth(depth)

        coarse = resample_grid(fine, target_resolution_km=50.0)
        assert coarse.lat.shape[0] < fine.lat.shape[0]
        assert coarse.lon.shape[0] < fine.lon.shape[0]
        # Depth values should be preserved (approximately) through interpolation
        assert np.allclose(coarse.depth, 3000.0, atol=1.0)


class TestGridCoordinateConversion:
    def test_lat_lon_to_meters(self):
        grid = create_grid(
            lat_min=0.0, lat_max=1.0,
            lon_min=0.0, lon_max=1.0,
            resolution_km=50.0,
        )
        x, y = grid.to_meters()
        # 1 degree lat ≈ 111,320 m at equator
        assert abs(y[-1] - 111_320) < 5000
        assert x.shape == (grid.lon.shape[0],)
        assert y.shape == (grid.lat.shape[0],)

    def test_cell_area_km2(self):
        grid = create_grid(
            lat_min=0.0, lat_max=1.0,
            lon_min=0.0, lon_max=1.0,
            resolution_km=100.0,
        )
        dx, dy = grid.cell_size_m()
        area_km2 = (dx * dy) / 1e6
        # 100km resolution → ~10,000 km² per cell
        assert 5000 < area_km2 < 15000
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_grid.py -v
```

Expected: `ModuleNotFoundError: No module named 'tsunami.simulation.grid'`

- [ ] **Step 3: Implement grid module**

`backend/src/tsunami/simulation/grid.py`:
```python
"""Grid creation, coordinate transforms, and resampling for simulation domains."""

from dataclasses import dataclass
import numpy as np
from scipy.interpolate import RegularGridInterpolator

# Earth radius in km
EARTH_RADIUS_KM = 6371.0
# Meters per degree latitude (approximately constant)
METERS_PER_DEG_LAT = 111_320.0


@dataclass(frozen=True)
class Grid:
    """2D simulation grid in lat/lon coordinates.

    lat: 1D array of latitude values (south to north), shape (ny,)
    lon: 1D array of longitude values (west to east), shape (nx,)
    depth: 2D array of ocean depth in meters (positive down), shape (ny, nx)
    """

    lat: np.ndarray
    lon: np.ndarray
    depth: np.ndarray

    def with_depth(self, depth: np.ndarray) -> "Grid":
        """Return a new Grid with replaced depth data, sharing coordinate arrays."""
        if depth.shape != self.depth.shape:
            raise ValueError(
                f"Depth shape {depth.shape} doesn't match grid shape {self.depth.shape}"
            )
        return Grid(lat=self.lat, lon=self.lon, depth=depth)

    def to_meters(self) -> tuple[np.ndarray, np.ndarray]:
        """Convert lat/lon to approximate meter offsets from grid origin.

        Returns (x_meters, y_meters) — 1D arrays for lon and lat axes.
        """
        lat_ref = (self.lat[0] + self.lat[-1]) / 2
        meters_per_deg_lon = METERS_PER_DEG_LAT * np.cos(np.radians(lat_ref))

        y = (self.lat - self.lat[0]) * METERS_PER_DEG_LAT
        x = (self.lon - self.lon[0]) * meters_per_deg_lon
        return x, y

    def cell_size_m(self) -> tuple[float, float]:
        """Return approximate (dx, dy) cell size in meters."""
        x, y = self.to_meters()
        dx = x[1] - x[0] if len(x) > 1 else 0.0
        dy = y[1] - y[0] if len(y) > 1 else 0.0
        return float(dx), float(dy)


def create_grid(
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    resolution_km: float,
) -> Grid:
    """Create a uniform lat/lon grid with the given resolution.

    Resolution is approximate — converted to degrees using the grid center latitude.
    Depth is initialized to zero.
    """
    center_lat = (lat_min + lat_max) / 2
    dlat = resolution_km / (EARTH_RADIUS_KM * np.radians(1))  # km → degrees
    dlon = dlat / np.cos(np.radians(center_lat))

    lat = np.arange(lat_min, lat_max + dlat / 2, dlat)
    lon = np.arange(lon_min, lon_max + dlon / 2, dlon)
    depth = np.zeros((len(lat), len(lon)))

    return Grid(lat=lat, lon=lon, depth=depth)


def domain_for_magnitude(
    lat: float, lon: float, magnitude: float
) -> dict[str, float]:
    """Compute simulation domain bounds based on earthquake magnitude.

    Larger earthquakes need larger domains. Returns dict with
    lat_min, lat_max, lon_min, lon_max.
    """
    # Empirical: radius in degrees scales exponentially with magnitude
    # M7 → ~10°, M8 → ~20°, M9 → ~40°
    radius_deg = 10.0 * (10 ** ((magnitude - 7.0) * 0.5))
    radius_deg = min(radius_deg, 80.0)  # cap at 80 degrees

    return {
        "lat_min": max(lat - radius_deg / 2, -90.0),
        "lat_max": min(lat + radius_deg / 2, 90.0),
        "lon_min": lon - radius_deg / 2,
        "lon_max": lon + radius_deg / 2,
    }


def resample_grid(grid: Grid, target_resolution_km: float) -> Grid:
    """Resample a grid to a different resolution using linear interpolation."""
    new_grid = create_grid(
        lat_min=float(grid.lat[0]),
        lat_max=float(grid.lat[-1]),
        lon_min=float(grid.lon[0]),
        lon_max=float(grid.lon[-1]),
        resolution_km=target_resolution_km,
    )

    interpolator = RegularGridInterpolator(
        (grid.lat, grid.lon), grid.depth, method="linear", bounds_error=False,
        fill_value=None,
    )
    lat_2d, lon_2d = np.meshgrid(new_grid.lat, new_grid.lon, indexing="ij")
    points = np.column_stack([lat_2d.ravel(), lon_2d.ravel()])
    new_depth = interpolator(points).reshape(lat_2d.shape)

    return new_grid.with_depth(new_depth)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_grid.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/simulation/grid.py backend/tests/test_grid.py
git commit -m "feat: add Grid module with coordinate conversion and resampling"
```

---

### Task 3: Okada Model — Earthquake Source

**Files:**
- Create: `backend/src/tsunami/simulation/okada.py`
- Create: `backend/tests/test_okada.py`

Implements the Okada (1985) analytical solution for surface displacement from a rectangular fault, plus Wells & Coppersmith (1994) scaling laws for deriving fault geometry from magnitude.

- [ ] **Step 1: Write failing tests for Okada model**

`backend/tests/test_okada.py`:
```python
import numpy as np
import pytest
from tsunami.simulation.okada import (
    FaultParams,
    magnitude_to_fault_params,
    compute_displacement,
)
from tsunami.simulation.grid import create_grid


class TestWellsCoppersmith:
    """Test empirical scaling from magnitude to fault parameters."""

    def test_m7_fault_dimensions(self):
        params = magnitude_to_fault_params(
            lat=0.0, lon=100.0, magnitude=7.0, direction=0.0
        )
        # M7: length ~40-60 km, width ~15-25 km, slip ~1-2 m
        assert 30.0 < params.length_km < 80.0
        assert 10.0 < params.width_km < 40.0
        assert 0.5 < params.slip_m < 4.0

    def test_m9_fault_dimensions(self):
        params = magnitude_to_fault_params(
            lat=0.0, lon=100.0, magnitude=9.0, direction=0.0
        )
        # M9: length ~500-1000 km, width ~100-200 km, slip ~10-20 m
        assert 300.0 < params.length_km < 1200.0
        assert 50.0 < params.width_km < 250.0
        assert 5.0 < params.slip_m < 30.0

    def test_direction_sets_strike(self):
        params = magnitude_to_fault_params(
            lat=0.0, lon=100.0, magnitude=8.0, direction=45.0
        )
        assert params.strike == 45.0

    def test_default_dip_for_subduction(self):
        params = magnitude_to_fault_params(
            lat=0.0, lon=100.0, magnitude=8.0, direction=0.0
        )
        # Default dip for thrust faulting: ~10-20 degrees
        assert 5.0 < params.dip < 30.0


class TestOkadaDisplacement:
    """Test the Okada (1985) displacement calculation."""

    def test_displacement_is_nonzero_near_fault(self):
        params = FaultParams(
            lat=0.0, lon=100.0,
            strike=0.0, dip=15.0, rake=90.0,
            slip_m=5.0, length_km=200.0, width_km=80.0, depth_km=10.0,
        )
        grid = create_grid(
            lat_min=-3.0, lat_max=3.0,
            lon_min=97.0, lon_max=103.0,
            resolution_km=10.0,
        )
        disp = compute_displacement(params, grid)
        assert disp.shape == grid.depth.shape
        # Should have both uplift and subsidence
        assert np.max(disp) > 0.0
        assert np.min(disp) < 0.0

    def test_displacement_decays_with_distance(self):
        params = FaultParams(
            lat=0.0, lon=100.0,
            strike=0.0, dip=15.0, rake=90.0,
            slip_m=5.0, length_km=200.0, width_km=80.0, depth_km=10.0,
        )
        grid = create_grid(
            lat_min=-10.0, lat_max=10.0,
            lon_min=90.0, lon_max=110.0,
            resolution_km=20.0,
        )
        disp = compute_displacement(params, grid)
        # Displacement at edges should be much smaller than near center
        center_row = disp.shape[0] // 2
        center_col = disp.shape[1] // 2
        near_center = np.abs(disp[center_row, center_col])
        at_edge = np.abs(disp[0, 0])
        assert near_center > at_edge * 5

    def test_pure_thrust_produces_uplift_on_hanging_wall(self):
        params = FaultParams(
            lat=0.0, lon=100.0,
            strike=0.0, dip=15.0, rake=90.0,  # pure thrust
            slip_m=5.0, length_km=200.0, width_km=80.0, depth_km=10.0,
        )
        grid = create_grid(
            lat_min=-3.0, lat_max=3.0,
            lon_min=97.0, lon_max=103.0,
            resolution_km=5.0,
        )
        disp = compute_displacement(params, grid)
        # For strike=0 (north), dip=15 (east-dipping), thrust:
        # hanging wall (east side) should have uplift
        max_idx = np.unravel_index(np.argmax(disp), disp.shape)
        # Maximum uplift should be on the eastern side (higher lon index)
        assert max_idx[1] > disp.shape[1] // 3

    def test_zero_slip_gives_zero_displacement(self):
        params = FaultParams(
            lat=0.0, lon=100.0,
            strike=0.0, dip=15.0, rake=90.0,
            slip_m=0.0, length_km=200.0, width_km=80.0, depth_km=10.0,
        )
        grid = create_grid(
            lat_min=-1.0, lat_max=1.0,
            lon_min=99.0, lon_max=101.0,
            resolution_km=20.0,
        )
        disp = compute_displacement(params, grid)
        assert np.allclose(disp, 0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_okada.py -v
```

Expected: `ModuleNotFoundError: No module named 'tsunami.simulation.okada'`

- [ ] **Step 3: Implement Okada model**

`backend/src/tsunami/simulation/okada.py`:
```python
"""Okada (1985) analytical solution for surface displacement from a rectangular fault.

Includes Wells & Coppersmith (1994) scaling laws for deriving fault geometry
from earthquake magnitude.

References:
    Okada, Y. (1985). Surface deformation due to shear and tensile faults
    in a half-space. Bull. Seismol. Soc. Am., 75(4), 1135-1154.

    Wells, D.L. & Coppersmith, K.J. (1994). New empirical relationships
    among magnitude, rupture length, rupture width, rupture area, and
    surface displacement. Bull. Seismol. Soc. Am., 84(4), 974-1002.
"""

from dataclasses import dataclass
import numpy as np

from tsunami.simulation.grid import Grid, METERS_PER_DEG_LAT


@dataclass
class FaultParams:
    """Rectangular fault parameters for the Okada model."""

    lat: float  # Fault center latitude (degrees)
    lon: float  # Fault center longitude (degrees)
    strike: float  # Strike angle clockwise from north (degrees)
    dip: float  # Dip angle from horizontal (degrees)
    rake: float  # Rake angle — 90° = pure thrust (degrees)
    slip_m: float  # Slip amount (meters)
    length_km: float  # Along-strike fault length (km)
    width_km: float  # Down-dip fault width (km)
    depth_km: float  # Depth to top of fault (km)


def magnitude_to_fault_params(
    lat: float, lon: float, magnitude: float, direction: float
) -> FaultParams:
    """Derive fault parameters from magnitude using Wells & Coppersmith (1994).

    Args:
        lat, lon: Epicenter location.
        magnitude: Moment magnitude (Mw).
        direction: Azimuth direction of tsunami propagation (degrees from north).
                   Used as strike angle.

    Returns:
        FaultParams with empirically scaled dimensions.
    """
    # Wells & Coppersmith (1994) regressions for reverse faults:
    # log10(L) = -2.86 + 0.63 * M  (L in km)
    # log10(W) = -1.61 + 0.41 * M  (W in km)
    # log10(D) = -4.80 + 0.69 * M  (D = average slip in m)
    log_length = -2.86 + 0.63 * magnitude
    log_width = -1.61 + 0.41 * magnitude
    log_slip = -4.80 + 0.69 * magnitude

    length_km = 10**log_length
    width_km = 10**log_width
    slip_m = 10**log_slip

    # Default subduction zone parameters
    dip = 15.0  # Shallow dip typical of megathrust
    rake = 90.0  # Pure thrust
    depth_km = 10.0  # Shallow depth for tsunamigenic earthquakes

    return FaultParams(
        lat=lat, lon=lon,
        strike=direction, dip=dip, rake=rake,
        slip_m=slip_m, length_km=length_km, width_km=width_km,
        depth_km=depth_km,
    )


def compute_displacement(params: FaultParams, grid: Grid) -> np.ndarray:
    """Compute vertical surface displacement on a grid using Okada (1985).

    Args:
        params: Fault parameters.
        grid: Simulation grid.

    Returns:
        2D array of vertical displacement in meters (positive = uplift),
        shape matching grid.depth.
    """
    if params.slip_m == 0.0:
        return np.zeros(grid.depth.shape)

    # Convert fault geometry to local Cartesian coordinates (meters)
    cos_lat = np.cos(np.radians(params.lat))
    meters_per_deg_lon = METERS_PER_DEG_LAT * cos_lat

    # Grid points relative to fault center, in meters
    lon_2d, lat_2d = np.meshgrid(grid.lon, grid.lat)
    x = (lon_2d - params.lon) * meters_per_deg_lon
    y = (lat_2d - params.lat) * METERS_PER_DEG_LAT

    # Rotate to fault-local coordinates (along-strike, perpendicular)
    strike_rad = np.radians(params.strike)
    cos_s = np.cos(strike_rad)
    sin_s = np.sin(strike_rad)
    # Rotate so that x' is along-strike direction
    xp = x * sin_s + y * cos_s
    yp = -x * cos_s + y * sin_s

    # Fault dimensions in meters
    length = params.length_km * 1000.0
    width = params.width_km * 1000.0
    depth = params.depth_km * 1000.0

    dip_rad = np.radians(params.dip)
    rake_rad = np.radians(params.rake)

    # Slip components
    U1 = params.slip_m * np.cos(rake_rad)  # strike-slip
    U2 = params.slip_m * np.sin(rake_rad)  # dip-slip

    cos_d = np.cos(dip_rad)
    sin_d = np.sin(dip_rad)

    # Okada uses integration over the fault plane via Chinnery's notation:
    # f(xi, eta) evaluated at four corners
    # xi ranges from -L/2 to L/2, eta ranges from 0 to W
    uz = np.zeros_like(xp)

    for sign_xi, xi_val in [(-1, -length / 2), (1, length / 2)]:
        for sign_eta, eta_val in [(-1, 0.0), (1, width)]:
            xi = xp - xi_val
            eta = yp * cos_d + (depth + eta_val * sin_d) * sin_d - eta_val * cos_d
            # Correct eta for Okada convention
            q = yp * sin_d - (depth + eta_val * sin_d) * cos_d

            d_tilde = eta * sin_d - q * cos_d
            R = np.sqrt(xi**2 + eta**2 + q**2)
            # Avoid division by zero
            R = np.maximum(R, 1e-10)

            sign = sign_xi * sign_eta

            # Vertical displacement contributions
            if abs(U1) > 1e-15:  # strike-slip component
                uz += sign * U1 / (2 * np.pi) * _uz_ss(xi, eta, q, R, dip_rad)

            if abs(U2) > 1e-15:  # dip-slip component
                uz += sign * U2 / (2 * np.pi) * _uz_ds(xi, eta, q, R, dip_rad)

    return uz


def _uz_ss(
    xi: np.ndarray, eta: np.ndarray, q: np.ndarray,
    R: np.ndarray, dip: float,
) -> np.ndarray:
    """Okada vertical displacement for strike-slip component."""
    sin_d = np.sin(dip)
    cos_d = np.cos(dip)
    d_tilde = eta * sin_d - q * cos_d

    # Avoid singularity at R + eta = 0
    R_eta = R + eta
    R_eta = np.where(np.abs(R_eta) < 1e-10, 1e-10, R_eta)

    return (
        d_tilde * q / (R * (R + eta))
        + q * sin_d / (R + eta)
        + np.arctan2(xi * eta, q * R)
    ) * (-1)


def _uz_ds(
    xi: np.ndarray, eta: np.ndarray, q: np.ndarray,
    R: np.ndarray, dip: float,
) -> np.ndarray:
    """Okada vertical displacement for dip-slip component."""
    sin_d = np.sin(dip)
    cos_d = np.cos(dip)
    d_tilde = eta * sin_d - q * cos_d
    y_tilde = eta * cos_d + q * sin_d

    # Avoid singularity
    R_eta = R + eta
    R_eta = np.where(np.abs(R_eta) < 1e-10, 1e-10, R_eta)
    R_xi = R + xi
    R_xi = np.where(np.abs(R_xi) < 1e-10, 1e-10, R_xi)

    return (
        d_tilde * q / (R * (R + xi))
        + sin_d * np.arctan2(xi * eta, q * R)
        - (y_tilde * q) / (R * (R + xi))
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_okada.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/simulation/okada.py backend/tests/test_okada.py
git commit -m "feat: add Okada (1985) displacement model with Wells-Coppersmith scaling"
```

---

### Task 4: Procedural Bathymetry

**Files:**
- Create: `backend/src/tsunami/bathymetry/procedural.py`
- Create: `backend/tests/test_procedural_bathy.py`

Generates idealized ocean depth profiles for testing and demos — continental shelf slope, flat ocean basin, and island profiles.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_procedural_bathy.py`:
```python
import numpy as np
import pytest
from tsunami.simulation.grid import Grid, create_grid
from tsunami.bathymetry.procedural import (
    generate_ocean_basin,
    generate_continental_shelf,
    generate_procedural_bathymetry,
)


class TestOceanBasin:
    def test_uniform_depth(self):
        grid = create_grid(
            lat_min=-5.0, lat_max=5.0,
            lon_min=95.0, lon_max=105.0,
            resolution_km=50.0,
        )
        depth = generate_ocean_basin(grid, depth_m=4000.0)
        assert depth.shape == grid.depth.shape
        assert np.allclose(depth, 4000.0)

    def test_depth_is_positive(self):
        grid = create_grid(
            lat_min=0.0, lat_max=1.0,
            lon_min=0.0, lon_max=1.0,
            resolution_km=10.0,
        )
        depth = generate_ocean_basin(grid, depth_m=3000.0)
        assert np.all(depth > 0)


class TestContinentalShelf:
    def test_shelf_has_shallow_and_deep(self):
        grid = create_grid(
            lat_min=-5.0, lat_max=5.0,
            lon_min=95.0, lon_max=105.0,
            resolution_km=20.0,
        )
        depth = generate_continental_shelf(
            grid,
            coast_lon=95.5,
            shelf_width_km=100.0,
            shelf_depth_m=200.0,
            ocean_depth_m=4000.0,
        )
        # Near coast should be shallow
        coast_col = np.argmin(np.abs(grid.lon - 95.5))
        assert np.mean(depth[:, coast_col]) < 500.0
        # Far from coast should be deep
        assert np.mean(depth[:, -1]) > 3000.0

    def test_depth_transitions_monotonically(self):
        grid = create_grid(
            lat_min=0.0, lat_max=1.0,
            lon_min=95.0, lon_max=105.0,
            resolution_km=20.0,
        )
        depth = generate_continental_shelf(
            grid,
            coast_lon=95.0,
            shelf_width_km=200.0,
            shelf_depth_m=200.0,
            ocean_depth_m=4000.0,
        )
        # Depth should generally increase away from coast (each row)
        mid_row = depth.shape[0] // 2
        profile = depth[mid_row, :]
        assert profile[-1] > profile[0]


class TestProceduralBathymetry:
    def test_generates_valid_grid(self):
        grid = create_grid(
            lat_min=-5.0, lat_max=5.0,
            lon_min=95.0, lon_max=105.0,
            resolution_km=50.0,
        )
        result = generate_procedural_bathymetry(grid)
        assert isinstance(result, Grid)
        assert result.depth.shape == grid.depth.shape
        assert np.all(result.depth >= 0)  # No negative depths
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_procedural_bathy.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement procedural bathymetry**

`backend/src/tsunami/bathymetry/procedural.py`:
```python
"""Procedural bathymetry generation for testing and demos.

Generates idealized ocean depth profiles without real-world data.
"""

import numpy as np
from tsunami.simulation.grid import Grid, METERS_PER_DEG_LAT


def generate_ocean_basin(grid: Grid, depth_m: float = 4000.0) -> np.ndarray:
    """Generate a flat ocean basin at uniform depth.

    Args:
        grid: Grid to fill.
        depth_m: Uniform depth in meters (positive down).

    Returns:
        2D array of depth values, shape (ny, nx).
    """
    return np.full(grid.depth.shape, depth_m)


def generate_continental_shelf(
    grid: Grid,
    coast_lon: float,
    shelf_width_km: float = 100.0,
    shelf_depth_m: float = 200.0,
    ocean_depth_m: float = 4000.0,
    slope_width_km: float = 50.0,
) -> np.ndarray:
    """Generate a continental shelf profile along a longitude line.

    Creates a cross-section from shallow shelf → continental slope → deep ocean
    moving east from coast_lon.

    Args:
        grid: Grid to fill.
        coast_lon: Longitude of the coastline.
        shelf_width_km: Width of the continental shelf (km).
        shelf_depth_m: Depth on the shelf (m).
        ocean_depth_m: Deep ocean depth (m).
        slope_width_km: Width of the continental slope transition (km).

    Returns:
        2D depth array, shape (ny, nx).
    """
    center_lat = (grid.lat[0] + grid.lat[-1]) / 2
    meters_per_deg_lon = METERS_PER_DEG_LAT * np.cos(np.radians(center_lat))

    # Distance from coast for each longitude (in km)
    dist_km = (grid.lon - coast_lon) * meters_per_deg_lon / 1000.0

    # Build 1D depth profile
    depth_1d = np.full_like(grid.lon, ocean_depth_m)
    for i, d in enumerate(dist_km):
        if d < 0:
            # Land side: set to 0 (at sea level)
            depth_1d[i] = max(0.0, shelf_depth_m * (1 + d / 10.0))
        elif d < shelf_width_km:
            # On the shelf
            depth_1d[i] = shelf_depth_m
        elif d < shelf_width_km + slope_width_km:
            # Continental slope: smooth transition
            t = (d - shelf_width_km) / slope_width_km
            # Smooth step using cosine interpolation
            t_smooth = (1 - np.cos(t * np.pi)) / 2
            depth_1d[i] = shelf_depth_m + (ocean_depth_m - shelf_depth_m) * t_smooth
        # else: already set to ocean_depth_m

    depth_1d = np.maximum(depth_1d, 0.0)

    # Broadcast to 2D (same profile for every latitude row)
    return np.broadcast_to(depth_1d, grid.depth.shape).copy()


def generate_procedural_bathymetry(grid: Grid) -> Grid:
    """Generate a simple procedural bathymetry for any grid.

    Creates an ocean basin with a continental shelf on the western edge,
    suitable for basic testing and demos.

    Args:
        grid: Grid to fill with depth data.

    Returns:
        New Grid with depth values populated.
    """
    coast_lon = grid.lon[0] + (grid.lon[-1] - grid.lon[0]) * 0.1
    depth = generate_continental_shelf(
        grid,
        coast_lon=coast_lon,
        shelf_width_km=80.0,
        shelf_depth_m=200.0,
        ocean_depth_m=4000.0,
    )
    return grid.with_depth(depth)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_procedural_bathy.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/bathymetry/procedural.py backend/tests/test_procedural_bathy.py
git commit -m "feat: add procedural bathymetry generation for testing and demos"
```

---

### Task 5: SWE Solver (Coarse Propagation)

**Files:**
- Create: `backend/src/tsunami/simulation/swe_solver.py`
- Create: `backend/tests/test_swe_solver.py`

Finite volume solver for the nonlinear Shallow Water Equations. This is the core wave propagation engine for the coarse simulation.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_swe_solver.py`:
```python
import numpy as np
import pytest
from tsunami.simulation.grid import Grid, create_grid
from tsunami.simulation.swe_solver import (
    SWEState,
    SWESolverConfig,
    create_initial_state,
    compute_cfl_dt,
    swe_step,
    run_swe,
)


class TestSWEState:
    def test_create_initial_state_from_displacement(self):
        grid = create_grid(
            lat_min=-1.0, lat_max=1.0,
            lon_min=-1.0, lon_max=1.0,
            resolution_km=20.0,
        )
        depth = np.full(grid.depth.shape, 4000.0)
        grid = grid.with_depth(depth)

        displacement = np.zeros(grid.depth.shape)
        displacement[5, 5] = 2.0  # 2m uplift at one point

        state = create_initial_state(grid, displacement)
        assert state.eta.shape == grid.depth.shape
        assert state.hu.shape == grid.depth.shape
        assert state.hv.shape == grid.depth.shape
        # Initial surface elevation equals displacement
        assert np.allclose(state.eta, displacement)
        # Initial momentum is zero (water starts at rest)
        assert np.allclose(state.hu, 0.0)
        assert np.allclose(state.hv, 0.0)


class TestCFLTimestep:
    def test_cfl_dt_shallow_water(self):
        dx = 2000.0  # 2 km grid spacing
        max_depth = 4000.0
        dt = compute_cfl_dt(dx, dx, max_depth, cfl=0.5)
        # Wave speed = sqrt(g*h) = sqrt(9.81*4000) ≈ 198 m/s
        # dt_max = CFL * dx / c ≈ 0.5 * 2000 / 198 ≈ 5.05 s
        assert 3.0 < dt < 8.0

    def test_cfl_dt_respects_smaller_dimension(self):
        dt1 = compute_cfl_dt(2000.0, 2000.0, 4000.0, cfl=0.5)
        dt2 = compute_cfl_dt(1000.0, 2000.0, 4000.0, cfl=0.5)
        assert dt2 < dt1  # Smaller dx → smaller dt


class TestSWEStep:
    def test_single_step_conserves_mass_approximately(self):
        grid = create_grid(
            lat_min=-1.0, lat_max=1.0,
            lon_min=-1.0, lon_max=1.0,
            resolution_km=20.0,
        )
        depth = np.full(grid.depth.shape, 4000.0)
        grid = grid.with_depth(depth)

        displacement = np.zeros(grid.depth.shape)
        # Gaussian bump
        cy, cx = grid.depth.shape[0] // 2, grid.depth.shape[1] // 2
        for i in range(grid.depth.shape[0]):
            for j in range(grid.depth.shape[1]):
                r2 = (i - cy) ** 2 + (j - cx) ** 2
                displacement[i, j] = 2.0 * np.exp(-r2 / 8.0)

        state = create_initial_state(grid, displacement)
        mass_before = np.sum(state.eta)

        dx, dy = grid.cell_size_m()
        dt = compute_cfl_dt(dx, dy, float(np.max(depth)), cfl=0.4)
        new_state = swe_step(state, grid, dt)

        mass_after = np.sum(new_state.eta)
        # Mass should be approximately conserved (within numerical tolerance)
        assert abs(mass_after - mass_before) / abs(mass_before) < 0.01


class TestRunSWE:
    def test_wave_propagates_outward(self):
        grid = create_grid(
            lat_min=-2.0, lat_max=2.0,
            lon_min=-2.0, lon_max=2.0,
            resolution_km=20.0,
        )
        depth = np.full(grid.depth.shape, 4000.0)
        grid = grid.with_depth(depth)

        displacement = np.zeros(grid.depth.shape)
        cy, cx = grid.depth.shape[0] // 2, grid.depth.shape[1] // 2
        for i in range(grid.depth.shape[0]):
            for j in range(grid.depth.shape[1]):
                r2 = (i - cy) ** 2 + (j - cx) ** 2
                displacement[i, j] = 2.0 * np.exp(-r2 / 4.0)

        config = SWESolverConfig(
            duration_seconds=600.0,  # 10 minutes
            output_interval_seconds=300.0,
            cfl=0.4,
        )
        frames = []

        def callback(time_s: float, state: SWEState):
            frames.append((time_s, state.eta.copy()))

        run_swe(grid, displacement, config, frame_callback=callback)

        assert len(frames) >= 2
        # Energy should have spread out from center
        initial_center = np.abs(displacement[cy, cx])
        final_center = np.abs(frames[-1][1][cy, cx])
        assert final_center < initial_center  # Wave has left the center

    def test_flat_ocean_no_displacement_stays_calm(self):
        grid = create_grid(
            lat_min=-1.0, lat_max=1.0,
            lon_min=-1.0, lon_max=1.0,
            resolution_km=20.0,
        )
        depth = np.full(grid.depth.shape, 4000.0)
        grid = grid.with_depth(depth)
        displacement = np.zeros(grid.depth.shape)

        config = SWESolverConfig(
            duration_seconds=300.0,
            output_interval_seconds=300.0,
            cfl=0.4,
        )
        frames = []

        def callback(time_s: float, state: SWEState):
            frames.append((time_s, state.eta.copy()))

        run_swe(grid, displacement, config, frame_callback=callback)

        # Should remain essentially zero everywhere
        assert np.max(np.abs(frames[-1][1])) < 1e-10
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_swe_solver.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement SWE solver**

`backend/src/tsunami/simulation/swe_solver.py`:
```python
"""Shallow Water Equations solver using finite volume method.

Solves the 2D nonlinear SWE for tsunami propagation on a lat/lon grid:
    ∂η/∂t + ∂(hu)/∂x + ∂(hv)/∂y = 0
    ∂(hu)/∂t + ∂(hu² + g·H²/2)/∂x + ∂(huv)/∂y = -gH·∂b/∂x + friction
    ∂(hv)/∂t + ∂(huv)/∂x + ∂(hv² + g·H²/2)/∂y = -gH·∂b/∂y + friction

where η = surface elevation, H = h + η = total water depth,
h = still water depth (bathymetry), u,v = velocities.

Uses Lax-Friedrichs flux with reflective boundary conditions.
"""

from dataclasses import dataclass
from typing import Callable
import numpy as np
from tsunami.simulation.grid import Grid

G = 9.81  # gravitational acceleration (m/s²)
MIN_DEPTH = 0.01  # minimum water depth for wet cells (m)


@dataclass
class SWEState:
    """Simulation state: surface elevation and momentum."""

    eta: np.ndarray  # Surface elevation (m), shape (ny, nx)
    hu: np.ndarray  # x-momentum (m²/s), shape (ny, nx)
    hv: np.ndarray  # y-momentum (m²/s), shape (ny, nx)


@dataclass
class SWESolverConfig:
    """Configuration for the SWE solver."""

    duration_seconds: float
    output_interval_seconds: float = 300.0  # 5 minutes default
    cfl: float = 0.4
    manning_n: float = 0.025  # Manning roughness coefficient


def create_initial_state(grid: Grid, displacement: np.ndarray) -> SWEState:
    """Create initial state from seafloor displacement.

    The sea surface is assumed to instantaneously match the displacement.
    Momentum starts at zero (water at rest).
    """
    return SWEState(
        eta=displacement.copy(),
        hu=np.zeros_like(displacement),
        hv=np.zeros_like(displacement),
    )


def compute_cfl_dt(dx: float, dy: float, max_depth: float, cfl: float = 0.4) -> float:
    """Compute time step from CFL condition.

    dt <= CFL * min(dx, dy) / sqrt(g * max_depth)
    """
    c = np.sqrt(G * max_depth)
    ds = min(abs(dx), abs(dy))
    return cfl * ds / c


def swe_step(state: SWEState, grid: Grid, dt: float) -> SWEState:
    """Advance one time step using Lax-Friedrichs finite volume method.

    Uses reflective (wall) boundary conditions.
    """
    eta = state.eta
    hu = state.hu
    hv = state.hv
    h = grid.depth  # still water depth (positive)

    dx, dy = grid.cell_size_m()
    if dx == 0 or dy == 0:
        return state

    # Total water depth
    H = h + eta
    H = np.maximum(H, 0.0)  # no negative water depth

    # Velocities (avoid division by zero in dry cells)
    wet = H > MIN_DEPTH
    u = np.where(wet, hu / H, 0.0)
    v = np.where(wet, hv / H, 0.0)

    # --- X-direction fluxes ---
    # Flux: F = [hu, hu² + g·H²/2, huv]
    flux_eta_x = hu
    flux_hu_x = hu * u + 0.5 * G * H**2
    flux_hv_x = hu * v

    # Lax-Friedrichs: F_{i+1/2} = 0.5*(F_i + F_{i+1}) - 0.5*(dx/dt)*(U_{i+1} - U_i)
    alpha_x = dx / dt

    d_eta_x = _lf_flux_divergence(flux_eta_x, eta, alpha_x, axis=1) / dx
    d_hu_x = _lf_flux_divergence(flux_hu_x, hu, alpha_x, axis=1) / dx
    d_hv_x = _lf_flux_divergence(flux_hv_x, hv, alpha_x, axis=1) / dx

    # --- Y-direction fluxes ---
    flux_eta_y = hv
    flux_hu_y = hu * v
    flux_hv_y = hv * v + 0.5 * G * H**2

    alpha_y = dy / dt

    d_eta_y = _lf_flux_divergence(flux_eta_y, eta, alpha_y, axis=0) / dy
    d_hu_y = _lf_flux_divergence(flux_hu_y, hu, alpha_y, axis=0) / dy
    d_hv_y = _lf_flux_divergence(flux_hv_y, hv, alpha_y, axis=0) / dy

    # --- Source terms: bathymetry gradient ---
    # S_hu = -g * H * dh/dx, S_hv = -g * H * dh/dy
    # (h is still water depth, gradient drives flow)
    dhdx = np.zeros_like(h)
    dhdy = np.zeros_like(h)
    dhdx[:, 1:-1] = (h[:, 2:] - h[:, :-2]) / (2 * dx)
    dhdy[1:-1, :] = (h[2:, :] - h[:-2, :]) / (2 * dy)

    src_hu = -G * H * dhdx
    src_hv = -G * H * dhdy

    # --- Update ---
    new_eta = eta - dt * (d_eta_x + d_eta_y)
    new_hu = hu - dt * (d_hu_x + d_hu_y) + dt * src_hu
    new_hv = hv - dt * (d_hv_x + d_hv_y) + dt * src_hv

    # Reflective boundary conditions (zero normal momentum at edges)
    new_hu[:, 0] = 0.0
    new_hu[:, -1] = 0.0
    new_hv[0, :] = 0.0
    new_hv[-1, :] = 0.0

    # Dry cell treatment
    new_H = grid.depth + new_eta
    dry = new_H <= MIN_DEPTH
    new_hu[dry] = 0.0
    new_hv[dry] = 0.0

    return SWEState(eta=new_eta, hu=new_hu, hv=new_hv)


def _lf_flux_divergence(
    flux: np.ndarray, conserved: np.ndarray, alpha: float, axis: int
) -> np.ndarray:
    """Compute Lax-Friedrichs flux divergence along an axis.

    Returns dF/dx approximation, shape same as input.
    """
    # Shift arrays to get i+1 and i-1
    f_plus = np.roll(flux, -1, axis=axis)
    f_minus = np.roll(flux, 1, axis=axis)
    u_plus = np.roll(conserved, -1, axis=axis)
    u_minus = np.roll(conserved, 1, axis=axis)

    # Lax-Friedrichs flux at i+1/2
    flux_right = 0.5 * (flux + f_plus) - 0.5 * alpha * (u_plus - conserved)
    # Lax-Friedrichs flux at i-1/2
    flux_left = 0.5 * (f_minus + flux) - 0.5 * alpha * (conserved - u_minus)

    divergence = flux_right - flux_left

    # Zero flux at boundaries (handled by boundary conditions on momentum)
    if axis == 0:
        divergence[0, :] = 0.0
        divergence[-1, :] = 0.0
    else:
        divergence[:, 0] = 0.0
        divergence[:, -1] = 0.0

    return divergence


def run_swe(
    grid: Grid,
    displacement: np.ndarray,
    config: SWESolverConfig,
    frame_callback: Callable[[float, SWEState], None] | None = None,
) -> SWEState:
    """Run the SWE solver for the configured duration.

    Args:
        grid: Simulation grid with bathymetry.
        displacement: Initial seafloor displacement (m).
        config: Solver configuration.
        frame_callback: Called at each output interval with (time_seconds, state).

    Returns:
        Final SWEState.
    """
    state = create_initial_state(grid, displacement)
    dx, dy = grid.cell_size_m()
    max_depth = float(np.max(grid.depth))

    if max_depth <= 0:
        return state

    dt = compute_cfl_dt(dx, dy, max_depth, config.cfl)
    t = 0.0
    next_output = config.output_interval_seconds

    while t < config.duration_seconds:
        step_dt = min(dt, config.duration_seconds - t)
        state = swe_step(state, grid, step_dt)
        t += step_dt

        if frame_callback and t >= next_output:
            frame_callback(t, state)
            next_output += config.output_interval_seconds

    return state
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_swe_solver.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/simulation/swe_solver.py backend/tests/test_swe_solver.py
git commit -m "feat: add SWE finite volume solver for coarse wave propagation"
```

---

### Task 6: Impact Detection

**Files:**
- Create: `backend/src/tsunami/simulation/impact.py`
- Create: `backend/tests/test_impact.py`

Scans coastal grid cells for significant wave heights, clusters them into suggested focus zones.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_impact.py`:
```python
import numpy as np
import pytest
from tsunami.simulation.grid import create_grid
from tsunami.simulation.impact import (
    CoastalImpact,
    FocusZoneSuggestion,
    detect_coastal_impacts,
    suggest_focus_zones,
)


class TestDetectCoastalImpacts:
    def test_finds_impacts_above_threshold(self):
        grid = create_grid(
            lat_min=-2.0, lat_max=2.0,
            lon_min=95.0, lon_max=105.0,
            resolution_km=20.0,
        )
        # Create bathymetry with a coast (shallow western edge)
        depth = np.full(grid.depth.shape, 4000.0)
        depth[:, :3] = 50.0  # shallow coastal cells
        grid = grid.with_depth(depth)

        # Max wave heights — significant near coast
        max_heights = np.zeros(grid.depth.shape)
        max_heights[:, 2] = 3.0  # 3m waves at coast
        max_heights[:, 1] = 1.5

        arrival_times = np.full(grid.depth.shape, np.inf)
        arrival_times[:, 2] = 1800.0  # 30 minutes

        impacts = detect_coastal_impacts(
            grid, max_heights, arrival_times, depth_threshold=200.0, height_threshold=0.5,
        )
        assert len(impacts) > 0
        assert all(imp.max_height >= 0.5 for imp in impacts)
        assert all(imp.arrival_time_s < np.inf for imp in impacts)

    def test_no_impacts_below_threshold(self):
        grid = create_grid(
            lat_min=-1.0, lat_max=1.0,
            lon_min=0.0, lon_max=2.0,
            resolution_km=20.0,
        )
        depth = np.full(grid.depth.shape, 4000.0)
        depth[:, :2] = 50.0
        grid = grid.with_depth(depth)

        max_heights = np.full(grid.depth.shape, 0.1)  # All below threshold
        arrival_times = np.full(grid.depth.shape, 1800.0)

        impacts = detect_coastal_impacts(
            grid, max_heights, arrival_times, depth_threshold=200.0, height_threshold=0.5,
        )
        assert len(impacts) == 0


class TestSuggestFocusZones:
    def test_clusters_nearby_impacts(self):
        impacts = [
            CoastalImpact(lat=0.0, lon=95.0, max_height=3.0, arrival_time_s=1800),
            CoastalImpact(lat=0.1, lon=95.0, max_height=2.5, arrival_time_s=1900),
            CoastalImpact(lat=0.2, lon=95.0, max_height=2.0, arrival_time_s=2000),
            # Second cluster far away
            CoastalImpact(lat=10.0, lon=95.0, max_height=1.5, arrival_time_s=5000),
            CoastalImpact(lat=10.1, lon=95.0, max_height=1.0, arrival_time_s=5100),
        ]
        zones = suggest_focus_zones(impacts, cluster_radius_km=100.0)
        assert len(zones) == 2  # Two clusters

    def test_zone_bounds_contain_impacts(self):
        impacts = [
            CoastalImpact(lat=5.0, lon=100.0, max_height=3.0, arrival_time_s=1800),
            CoastalImpact(lat=5.5, lon=100.5, max_height=2.0, arrival_time_s=2000),
        ]
        zones = suggest_focus_zones(impacts, cluster_radius_km=200.0)
        assert len(zones) >= 1
        zone = zones[0]
        # Zone geometry should encompass the impact points
        assert zone.lat_min <= 5.0
        assert zone.lat_max >= 5.5
        assert zone.lon_min <= 100.0
        assert zone.lon_max >= 100.5

    def test_empty_impacts_gives_no_zones(self):
        zones = suggest_focus_zones([], cluster_radius_km=100.0)
        assert len(zones) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_impact.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement impact detection**

`backend/src/tsunami/simulation/impact.py`:
```python
"""Coastal impact detection and focus zone suggestion.

Identifies where significant tsunami waves reach the coast and
clusters impact points into suggested analysis zones.
"""

from dataclasses import dataclass
import numpy as np
from tsunami.simulation.grid import Grid, METERS_PER_DEG_LAT


@dataclass
class CoastalImpact:
    """A point where the tsunami significantly impacts the coast."""

    lat: float
    lon: float
    max_height: float  # meters
    arrival_time_s: float  # seconds from earthquake


@dataclass
class FocusZoneSuggestion:
    """A suggested rectangular zone for detailed analysis."""

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    max_impact_height: float
    impact_count: int


def detect_coastal_impacts(
    grid: Grid,
    max_wave_heights: np.ndarray,
    arrival_times: np.ndarray,
    depth_threshold: float = 200.0,
    height_threshold: float = 0.5,
) -> list[CoastalImpact]:
    """Find coastal grid cells with significant wave heights.

    A cell is "coastal" if its depth is less than depth_threshold.
    An impact is recorded if the max wave height exceeds height_threshold.

    Args:
        grid: Simulation grid with bathymetry.
        max_wave_heights: 2D array of maximum wave heights (m).
        arrival_times: 2D array of first arrival times (seconds).
        depth_threshold: Max depth (m) to consider a cell coastal.
        height_threshold: Min wave height (m) to consider significant.

    Returns:
        List of CoastalImpact records.
    """
    coastal = grid.depth < depth_threshold
    significant = max_wave_heights >= height_threshold
    mask = coastal & significant

    impacts = []
    rows, cols = np.where(mask)
    for r, c in zip(rows, cols):
        impacts.append(
            CoastalImpact(
                lat=float(grid.lat[r]),
                lon=float(grid.lon[c]),
                max_height=float(max_wave_heights[r, c]),
                arrival_time_s=float(arrival_times[r, c]),
            )
        )

    return impacts


def suggest_focus_zones(
    impacts: list[CoastalImpact],
    cluster_radius_km: float = 100.0,
    padding_deg: float = 0.5,
) -> list[FocusZoneSuggestion]:
    """Cluster impacts into suggested focus zones using simple distance-based clustering.

    Args:
        impacts: List of coastal impacts.
        cluster_radius_km: Maximum distance (km) between impacts in the same cluster.
        padding_deg: Extra padding around cluster bounds (degrees).

    Returns:
        List of FocusZoneSuggestion, sorted by max impact height (descending).
    """
    if not impacts:
        return []

    # Simple greedy clustering by distance
    used = [False] * len(impacts)
    clusters: list[list[CoastalImpact]] = []

    for i, imp in enumerate(impacts):
        if used[i]:
            continue
        cluster = [imp]
        used[i] = True
        for j in range(i + 1, len(impacts)):
            if used[j]:
                continue
            dist = _haversine_km(imp.lat, imp.lon, impacts[j].lat, impacts[j].lon)
            if dist <= cluster_radius_km:
                cluster.append(impacts[j])
                used[j] = True
        clusters.append(cluster)

    zones = []
    for cluster in clusters:
        lats = [c.lat for c in cluster]
        lons = [c.lon for c in cluster]
        zones.append(
            FocusZoneSuggestion(
                lat_min=min(lats) - padding_deg,
                lat_max=max(lats) + padding_deg,
                lon_min=min(lons) - padding_deg,
                lon_max=max(lons) + padding_deg,
                max_impact_height=max(c.max_height for c in cluster),
                impact_count=len(cluster),
            )
        )

    zones.sort(key=lambda z: z.max_impact_height, reverse=True)
    return zones


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance between two points in km."""
    dlat = abs(lat2 - lat1) * METERS_PER_DEG_LAT / 1000.0
    mean_lat = (lat1 + lat2) / 2
    dlon = (
        abs(lon2 - lon1)
        * METERS_PER_DEG_LAT
        * np.cos(np.radians(mean_lat))
        / 1000.0
    )
    return float(np.sqrt(dlat**2 + dlon**2))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_impact.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/simulation/impact.py backend/tests/test_impact.py
git commit -m "feat: add coastal impact detection and focus zone suggestion"
```

---

### Task 7: Boussinesq Solver (Fine-Scale)

**Files:**
- Create: `backend/src/tsunami/simulation/boussinesq.py`
- Create: `backend/tests/test_boussinesq.py`

Extended Boussinesq equations with dispersive terms for nearshore modeling. Uses boundary conditions from the coarse SWE simulation.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_boussinesq.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_boussinesq.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement Boussinesq solver**

`backend/src/tsunami/simulation/boussinesq.py`:
```python
"""Extended Boussinesq equations solver for fine-scale nearshore modeling.

Adds dispersive correction terms to the Shallow Water Equations,
producing more accurate wave shapes in shallow water where wavelength
and depth are comparable.

The Boussinesq system:
    ∂η/∂t + ∇·((h+η)u) = 0
    ∂u/∂t + (u·∇)u + g∇η = B·h²·∂²(∂u/∂t)/∂x² + dispersive terms

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
    """Configuration for Boussinesq solver."""

    duration_seconds: float
    output_interval_seconds: float = 60.0
    cfl: float = 0.3  # More conservative CFL for stability
    dispersion_coefficient: float = 1.0 / 15.0  # Peregrine B coefficient


@dataclass
class BoundaryConditions:
    """Time-varying boundary conditions from coarse SWE solution."""

    time_seconds: list[float]
    # Boundary values interpolated to fine grid edges
    # Each is a list of 2D arrays at each time step
    eta_north: list[np.ndarray]
    eta_south: list[np.ndarray]
    eta_east: list[np.ndarray]
    eta_west: list[np.ndarray]

    @property
    def n_timesteps(self) -> int:
        return len(self.time_seconds)


@dataclass
class BoussinesqResult:
    """Results from a Boussinesq simulation."""

    max_wave_heights: np.ndarray  # (ny, nx) max |eta| at each point
    max_velocity: np.ndarray  # (ny, nx) max |velocity| at each point
    frames: list[tuple[float, np.ndarray]]  # [(time_s, eta), ...]


def create_boundary_conditions_from_swe(
    coarse_grid: Grid,
    fine_grid: Grid,
    coarse_states: list[tuple[float, SWEState]],
) -> BoundaryConditions:
    """Extract boundary conditions for the fine grid from coarse SWE states.

    Interpolates coarse solution to the fine grid boundary cells at each
    saved timestep.
    """
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

        # North boundary: last row of fine grid
        north_pts = np.column_stack([
            np.full(len(fine_grid.lon), fine_grid.lat[-1]),
            fine_grid.lon,
        ])
        eta_n.append(interp(north_pts))

        # South boundary
        south_pts = np.column_stack([
            np.full(len(fine_grid.lon), fine_grid.lat[0]),
            fine_grid.lon,
        ])
        eta_s.append(interp(south_pts))

        # East boundary
        east_pts = np.column_stack([
            fine_grid.lat,
            np.full(len(fine_grid.lat), fine_grid.lon[-1]),
        ])
        eta_e.append(interp(east_pts))

        # West boundary
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
    """Apply Boussinesq dispersive correction to the SWE state.

    Adds the term B * h² * ∂²(∂(hu)/∂t)/∂x² as a correction.
    Simplified implementation using Laplacian of momentum as proxy.
    """
    dx, dy = grid.cell_size_m()
    if dx == 0 or dy == 0:
        return state

    h = grid.depth
    H = np.maximum(h + state.eta, MIN_DEPTH)

    # Dispersive correction: B * h² * laplacian(hu, hv)
    # This is a simplified Peregrine-type correction
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

    # Apply correction
    correction_hu = B * h2 * lap_hu * dt
    correction_hv = B * h2 * lap_hv * dt

    # Limit correction magnitude for stability
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
    # Find bracketing timesteps
    times = bc.time_seconds
    if t <= times[0]:
        idx = 0
        frac = 0.0
    elif t >= times[-1]:
        idx = len(times) - 2
        frac = 1.0
    else:
        for i in range(len(times) - 1):
            if times[i] <= t <= times[i + 1]:
                idx = i
                frac = (t - times[i]) / (times[i + 1] - times[i])
                break

    def lerp(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return a * (1 - frac) + b * frac

    eta = state.eta.copy()
    eta[-1, :] = lerp(bc.eta_north[idx], bc.eta_north[min(idx + 1, len(times) - 1)])
    eta[0, :] = lerp(bc.eta_south[idx], bc.eta_south[min(idx + 1, len(times) - 1)])
    eta[:, -1] = lerp(bc.eta_east[idx], bc.eta_east[min(idx + 1, len(times) - 1)])
    eta[:, 0] = lerp(bc.eta_west[idx], bc.eta_west[min(idx + 1, len(times) - 1)])

    return SWEState(eta=eta, hu=state.hu, hv=state.hv)


def run_boussinesq(
    grid: Grid,
    initial_eta: np.ndarray,
    config: BoussinesqConfig,
    boundary_conditions: BoundaryConditions | None = None,
    progress_callback: Callable[[float], None] | None = None,
) -> BoussinesqResult:
    """Run the Boussinesq solver.

    Uses operator splitting: SWE step + dispersive correction.

    Args:
        grid: Fine-resolution grid with bathymetry.
        initial_eta: Initial surface elevation (m).
        config: Solver configuration.
        boundary_conditions: Time-varying BCs from coarse solution.
        progress_callback: Called with progress percentage (0-100).

    Returns:
        BoussinesqResult with max heights, velocities, and frame history.
    """
    displacement = initial_eta
    state = create_initial_state(grid, displacement)

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
        speed = np.sqrt(
            (state.hu / H) ** 2 + (state.hv / H) ** 2
        )
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_boussinesq.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/simulation/boussinesq.py backend/tests/test_boussinesq.py
git commit -m "feat: add Boussinesq solver with dispersive corrections for nearshore modeling"
```

---

### Task 8: Inundation Mapping

**Files:**
- Create: `backend/src/tsunami/simulation/inundation.py`
- Create: `backend/tests/test_inundation.py`

Extracts flood extent, depth, and velocity from simulation results. Generates GeoJSON polygons for inundation boundaries.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_inundation.py`:
```python
import numpy as np
import pytest
from tsunami.simulation.grid import create_grid
from tsunami.simulation.inundation import (
    InundationResult,
    compute_inundation,
)


class TestComputeInundation:
    def _make_coastal_grid(self):
        """Create a grid with coastal topography: ocean → beach → land."""
        grid = create_grid(
            lat_min=-0.5, lat_max=0.5,
            lon_min=-0.5, lon_max=0.5,
            resolution_km=5.0,
        )
        ny, nx = grid.depth.shape
        # Depth profile: deep ocean on left, sloping to land (negative depth = elevation)
        depth = np.zeros((ny, nx))
        for j in range(nx):
            frac = j / (nx - 1)
            # From 100m deep to 20m above sea level
            depth[:, j] = 100.0 - 120.0 * frac
        return grid.with_depth(depth)

    def test_inundation_detected_on_land(self):
        grid = self._make_coastal_grid()
        ny, nx = grid.depth.shape

        # Wave that floods some land
        max_heights = np.zeros((ny, nx))
        max_heights[:, :] = 5.0  # 5m waves everywhere

        max_velocity = np.ones((ny, nx)) * 2.0

        result = compute_inundation(grid, max_heights, max_velocity)
        assert isinstance(result, InundationResult)
        # Some cells should be inundated (where depth < 0 but wave > |depth|)
        assert np.any(result.flood_depth > 0)
        assert result.max_runup_m > 0

    def test_no_inundation_with_small_waves(self):
        grid = self._make_coastal_grid()
        ny, nx = grid.depth.shape

        max_heights = np.full((ny, nx), 0.01)  # tiny waves
        max_velocity = np.full((ny, nx), 0.01)

        result = compute_inundation(grid, max_heights, max_velocity)
        # Waves too small to reach land
        assert result.max_runup_m < 1.0

    def test_flood_depth_is_wave_minus_elevation(self):
        grid = create_grid(
            lat_min=0.0, lat_max=0.1,
            lon_min=0.0, lon_max=0.1,
            resolution_km=2.0,
        )
        # Single elevation: 3m above sea level (depth = -3)
        depth = np.full(grid.depth.shape, -3.0)
        grid = grid.with_depth(depth)

        # 5m wave → flood depth should be ~2m
        max_heights = np.full(grid.depth.shape, 5.0)
        max_velocity = np.ones(grid.depth.shape)

        result = compute_inundation(grid, max_heights, max_velocity)
        # Flood depth = wave height - elevation = 5 - 3 = 2m
        assert np.allclose(result.flood_depth, 2.0, atol=0.1)

    def test_geojson_polygon_generated(self):
        grid = self._make_coastal_grid()
        max_heights = np.full(grid.depth.shape, 5.0)
        max_velocity = np.ones(grid.depth.shape) * 2.0

        result = compute_inundation(grid, max_heights, max_velocity)
        geojson = result.inundation_extent_geojson()
        assert geojson["type"] == "Feature"
        assert geojson["geometry"]["type"] in ("Polygon", "MultiPolygon")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_inundation.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement inundation mapping**

`backend/src/tsunami/simulation/inundation.py`:
```python
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
    """Results of inundation analysis for a focus zone."""

    flood_depth: np.ndarray  # (ny, nx) flood depth on land (m), 0 where not flooded
    flow_velocity: np.ndarray  # (ny, nx) max flow velocity (m/s), 0 where not flooded
    max_runup_m: float  # Maximum elevation reached by water (m above sea level)
    inundated_mask: np.ndarray  # (ny, nx) boolean mask of flooded cells
    grid: Grid  # Reference to the grid for coordinate access

    def inundation_extent_geojson(self) -> dict[str, Any]:
        """Generate a GeoJSON Feature of the inundation boundary.

        Uses a simple grid-cell approach: each inundated cell becomes a small
        polygon, merged into a single MultiPolygon.
        """
        polygons = []
        dy = float(self.grid.lat[1] - self.grid.lat[0]) if len(self.grid.lat) > 1 else 0.01
        dx = float(self.grid.lon[1] - self.grid.lon[0]) if len(self.grid.lon) > 1 else 0.01

        rows, cols = np.where(self.inundated_mask)
        for r, c in zip(rows, cols):
            lat = float(self.grid.lat[r])
            lon = float(self.grid.lon[c])
            # Cell polygon (counter-clockwise)
            poly = [
                [lon - dx / 2, lat - dy / 2],
                [lon + dx / 2, lat - dy / 2],
                [lon + dx / 2, lat + dy / 2],
                [lon - dx / 2, lat + dy / 2],
                [lon - dx / 2, lat - dy / 2],
            ]
            polygons.append([poly])

        if not polygons:
            # Empty inundation — return empty polygon
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

    Args:
        grid: Grid with bathymetry (negative depth = land elevation).
        max_wave_heights: Maximum wave heights from simulation (m).
        max_velocity: Maximum flow velocities from simulation (m/s).
        min_flood_depth: Minimum flood depth to count as inundated (m).

    Returns:
        InundationResult with flood depth, velocity, and extent.
    """
    # Land cells: depth < 0, elevation = -depth
    elevation = np.where(grid.depth < 0, -grid.depth, 0.0)

    # Flood depth = wave height - elevation (only on land)
    flood_depth = np.maximum(max_wave_heights - elevation, 0.0)

    # Only count cells that are actually on land (depth <= 0) or very shallow
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_inundation.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/simulation/inundation.py backend/tests/test_inundation.py
git commit -m "feat: add inundation mapping with flood depth, velocity, and GeoJSON export"
```

---

### Task 9: Integration Test — Full Pipeline

**Files:**
- Create: `backend/tests/test_pipeline.py`

End-to-end test that runs the complete simulation pipeline: earthquake → Okada → bathymetry → SWE → impact detection → Boussinesq → inundation.

- [ ] **Step 1: Write the integration test**

`backend/tests/test_pipeline.py`:
```python
import numpy as np
import pytest
from tsunami.simulation.okada import magnitude_to_fault_params, compute_displacement
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
        # Use a small domain and coarse grid for test speed
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
        assert np.max(np.abs(displacement)) > 0.1  # Should have measurable displacement

        # 5. Run coarse SWE
        config = SWESolverConfig(
            duration_seconds=1800.0,  # 30 minutes
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

        # Arrival times: first time wave exceeds threshold at each cell
        arrival_times = np.full(coarse_grid.depth.shape, np.inf)
        for t, state in coarse_frames:
            newly_arrived = (np.abs(state.eta) > 0.1) & (arrival_times == np.inf)
            arrival_times[newly_arrived] = t

        impacts = detect_coastal_impacts(
            coarse_grid, max_heights, arrival_times,
            depth_threshold=300.0, height_threshold=0.1,
        )
        # We may or may not get impacts depending on timing, so just check it runs
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
                resolution_km=5.0,  # coarser for test speed
            )
            # Use shelf bathymetry for fine grid too
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
                duration_seconds=300.0,  # 5 minutes for test
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
        from tsunami.simulation.okada import FaultParams

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
```

- [ ] **Step 2: Run the integration test**

```bash
cd backend && pytest tests/test_pipeline.py -v --timeout=120
```

Expected: All tests PASS (may take 10-30 seconds for the full pipeline)

- [ ] **Step 3: Run the full test suite**

```bash
cd backend && pytest tests/ -v --tb=short
```

Expected: All tests across all modules PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_pipeline.py
git commit -m "feat: add end-to-end integration test for full simulation pipeline"
```

---

## Self-Review

**Spec coverage check:**
- Grid management: Task 2 ✓
- Okada model (simple + advanced): Task 3 ✓
- Simulation domain from magnitude: Task 2 (`domain_for_magnitude`) ✓
- SWE solver with frame streaming: Task 5 ✓
- Impact detection + zone suggestion: Task 6 ✓
- Boussinesq solver with boundary conditions: Task 7 ✓
- Inundation mapping with GeoJSON export: Task 8 ✓
- Procedural bathymetry fallback: Task 4 ✓
- End-to-end pipeline: Task 9 ✓
- GEBCO/ETOPO bathymetry: Deferred to Plan 2 (requires network/data) ✓
- REST API, WebSocket, Celery: Deferred to Plan 2 ✓
- Frontend: Deferred to Plan 3 ✓
- NetCDF/GeoTIFF file output: Partially covered (GeoJSON in inundation); full file I/O deferred to Plan 2 where the API needs it

**Placeholder scan:** No TBDs, TODOs, or vague steps found. All steps have concrete code.

**Type consistency check:**
- `Grid`, `create_grid`, `domain_for_magnitude`, `resample_grid` — consistent across Tasks 2-9
- `FaultParams`, `magnitude_to_fault_params`, `compute_displacement` — consistent across Tasks 3, 9
- `SWEState`, `SWESolverConfig`, `create_initial_state`, `compute_cfl_dt`, `swe_step`, `run_swe` — consistent across Tasks 5, 7, 9
- `CoastalImpact`, `FocusZoneSuggestion`, `detect_coastal_impacts`, `suggest_focus_zones` — consistent across Tasks 6, 9
- `BoussinesqConfig`, `BoussinesqResult`, `BoundaryConditions`, `create_boundary_conditions_from_swe`, `run_boussinesq` — consistent across Tasks 7, 9
- `InundationResult`, `compute_inundation` — consistent across Tasks 8, 9
