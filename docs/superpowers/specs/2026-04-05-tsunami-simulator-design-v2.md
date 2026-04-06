# Tsunami Simulator — Design Specification v2

> Supersedes v1. Key change: PyClaw/GeoClaw replaces custom Lax-Friedrichs SWE solver for coarse propagation. Custom Boussinesq solver retained for fine-scale nearshore modeling.

## Overview

A web-based tsunami simulation system using a two-level approach:
1. **Coarse propagation** — PyClaw with GeoClaw's augmented Roe Riemann solver on a ~2 km grid. Second-order accurate, handles bathymetry and dry states natively. Runs in-process for interactive speed.
2. **Fine-scale nearshore** — Custom Boussinesq solver with dispersive corrections on a ~100 m grid. Background worker job for detailed inundation analysis.

Serves educational/visualization and research/scientific use cases.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Web Frontend                           │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  2D Map View  │  │  3D Globe    │  │  Control Panel    │  │
│  │  (MapLibre)   │◄─►│  (CesiumJS)  │  │  - Earthquake src │  │
│  │  - Heatmaps   │  │  - Terrain   │  │  - Focus zones    │  │
│  │  - Contours   │  │  - Wave mesh │  │  - Results/Export  │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
│                         │ WebSocket + REST                   │
└─────────────────────────┼───────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────┐
│                    Docker Compose                            │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │              FastAPI Server                          │    │
│  │  ┌────────────┐ ┌────────────┐ ┌─────────────────┐  │    │
│  │  │ REST API   │ │ WebSocket  │ │ PyClaw SWE      │  │    │
│  │  │ /quakes    │ │ /ws/sim    │ │ Solver          │  │    │
│  │  │ /zones     │ │ (progress) │ │ (in-process)    │  │    │
│  │  │ /results   │ │            │ │                 │  │    │
│  │  └────────────┘ └────────────┘ └─────────────────┘  │    │
│  └─────────────────────┬───────────────────────────────┘    │
│                         │ Job Queue                          │
│  ┌──────────┐   ┌──────▼───────────────────────────────┐    │
│  │  Redis   │◄──│         Worker Process(es)            │    │
│  │          │   │  ┌─────────────────────────────────┐  │    │
│  └──────────┘   │  │  Boussinesq Solver (custom)     │  │    │
│                  │  │  + Inundation Mapper            │  │    │
│  ┌──────────┐   │  └─────────────────────────────────┘  │    │
│  │ SQLite   │   └──────────────────────────────────────┘    │
│  │ + Files  │                                                │
│  └──────────┘   ┌──────────────────────────────────────┐    │
│                  │        Bathymetry Data Service        │    │
│                  │  GEBCO/ETOPO cache + procedural       │    │
│                  └──────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Docker Compose Services

| Service | Role | Scaling |
|---------|------|---------|
| `backend` | FastAPI + PyClaw SWE solver (in-process) | Single |
| `worker` | Celery worker for Boussinesq jobs | Horizontal |
| `redis` | Job queue + result backend | Single |
| `frontend` | React dev server / nginx (prod) | Single |

## Simulation Pipeline

### Step 1: Earthquake Source Definition

**Simple mode** — lat/lon, magnitude, direction. System derives fault geometry via Wells & Coppersmith (1994).

**Advanced mode** — full Okada parameters: strike, dip, rake, slip, length, width, depth.

### Step 2: Okada Model — Seafloor Displacement

Okada (1985) analytical solution converts fault parameters into a 2D seafloor displacement field. This becomes the initial condition for wave propagation.

### Step 3: Simulation Domain

Domain automatically sized from earthquake magnitude (M7 → ~1000 km radius, M9 → full ocean basin). User can manually adjust.

### Step 4: Coarse Bathymetry Fetch

- **Primary**: GEBCO global grid (~450 m native, resampled to ~1–5 km)
- **Fallback**: Procedural generation (continental shelf profiles)
- Data cached locally after first download

### Step 5: PyClaw SWE Solver (Coarse, In-Process)

**This is the key change from v1.** Instead of a custom Lax-Friedrichs solver, we use PyClaw:

```python
from clawpack import pyclaw, riemann

solver = pyclaw.ClawSolver2D(riemann.shallow_roe_with_efix_2D)
solver.limiters = pyclaw.limiters.tvd.MC  # Second-order with MC limiter
solver.dimensional_split = True

# Domain from lat/lon grid converted to meters
domain = pyclaw.Domain([x_min, y_min], [x_max, y_max], [nx, ny])
solution = pyclaw.Solution(solver.num_eqn, domain)

# Set initial conditions from Okada displacement
# Set bathymetry as auxiliary variable
# Run via Controller with frame callbacks for WebSocket streaming
```

**Advantages over custom Lax-Friedrichs:**
- Second-order accurate with wave limiters (less diffusion)
- Proven Roe Riemann solver with proper wave decomposition
- Native handling of dry states and wet/dry interfaces
- Extensible to GeoClaw's augmented solver for bathymetry source terms
- Published, validated, peer-reviewed numerics

**PyClaw integration wrapper** (`backend/src/tsunami/simulation/swe_solver.py`):
- Translates our Grid + displacement into PyClaw Domain + Solution
- Configures solver, boundary conditions, and auxiliary data (bathymetry)
- Runs the Controller with a callback that converts PyClaw frames to our SWEState format
- Handles coordinate conversion (lat/lon → local Cartesian meters)

**Boundary conditions:**
- Wall (reflective) for land boundaries
- Extrapolation (absorbing) for open ocean edges — eliminates artificial edge reflections

**Outputs:**
- Wave height field time series (NumPy arrays, saved as NetCDF)
- Maximum wave height map
- Wave arrival time map
- Coastline impact list

### Step 6: Impact Detection

Scans coastal cells for wave heights above threshold. Clusters into suggested focus zones via spatial clustering. Suggestions pushed to frontend via WebSocket.

### Step 7: Focus Zone Selection

Three methods (all available):
1. Accept auto-detected zones
2. Pick from preset coastal locations
3. Draw custom polygons on map

### Step 8: High-Resolution Bathymetry Fetch

ETOPO or higher-res regional data (~50–100 m) for focus zones. Fallback to interpolated GEBCO or procedural.

### Step 9: Boussinesq Solver (Fine, Background Worker)

Custom solver using operator splitting: SWE step + dispersive Peregrine correction. One-way nesting — boundary conditions from coarse PyClaw solution.

**Outputs per focus zone:**
- Inundation extent (GeoJSON)
- Flood depth map (GeoTIFF)
- Flow velocity map (GeoTIFF)
- Maximum runup height
- Event timeline

## Data Model

```
Simulation
├── id: UUID
├── name: string
├── created_at: datetime
├── status: pending | running_coarse | coarse_complete | running_detail | complete | failed
│
├── EarthquakeSource
│   ├── lat, lon: float
│   ├── magnitude: float
│   ├── direction: float (azimuth, simple mode)
│   ├── depth_km: float
│   └── FaultParams (advanced mode, nullable)
│       ├── strike, dip, rake: float (degrees)
│       ├── slip: float (meters)
│       └── length, width: float (km)
│
├── CoarseConfig
│   ├── grid_resolution_km: float (default 2.0)
│   ├── duration_hours: float (default 6.0)
│   ├── bathymetry_source: "gebco" | "procedural"
│   └── solver_settings: {limiter, bc_type, cfl}
│
├── CoarseResult
│   ├── wave_height_field: path to NetCDF
│   ├── max_wave_heights: path to GeoTIFF
│   ├── arrival_times: path to GeoTIFF
│   ├── coastline_impacts: [{lat, lon, max_height, arrival_time}, ...]
│   └── suggested_zones: [FocusZone, ...]
│
├── FocusZone[]
│   ├── id: UUID
│   ├── name: string
│   ├── geometry: GeoJSON Polygon
│   ├── source: "auto" | "preset" | "user_drawn"
│   ├── grid_resolution_m: float (default 100)
│   └── status: pending | running | complete | failed
│
└── DetailResult[] (one per FocusZone)
    ├── zone_id: UUID
    ├── inundation_extent: path to GeoJSON
    ├── flood_depth: path to GeoTIFF
    ├── flow_velocity: path to GeoTIFF
    ├── max_runup_m: float
    └── timeline: [{time, wave_height, description}, ...]
```

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/simulations` | Create new simulation |
| `GET` | `/api/simulations` | List all simulations |
| `GET` | `/api/simulations/{id}` | Get simulation status & metadata |
| `DELETE` | `/api/simulations/{id}` | Delete simulation and results |
| `POST` | `/api/simulations/{id}/run-coarse` | Start coarse PyClaw simulation |
| `GET` | `/api/simulations/{id}/coarse-result` | Get coarse results |
| `POST` | `/api/simulations/{id}/focus-zones` | Add focus zone |
| `GET` | `/api/simulations/{id}/focus-zones` | List focus zones |
| `PUT` | `/api/simulations/{id}/focus-zones/{zid}` | Update zone |
| `DELETE` | `/api/simulations/{id}/focus-zones/{zid}` | Remove zone |
| `POST` | `/api/simulations/{id}/run-detail` | Start detailed analysis (all zones) |
| `POST` | `/api/simulations/{id}/focus-zones/{zid}/run` | Start single zone |
| `GET` | `/api/simulations/{id}/focus-zones/{zid}/result` | Get detail results |
| `GET` | `/api/simulations/{id}/export?format=geojson\|csv\|netcdf` | Export |
| `GET` | `/api/bathymetry/check?bounds=...` | Check data availability |
| `POST` | `/api/bathymetry/fetch` | Trigger download |
| `GET` | `/api/presets/locations` | List preset locations |

## WebSocket Protocol

`WS /api/ws/simulations/{id}`

| Type | Payload | When |
|------|---------|------|
| `coarse_progress` | `{step, total, time_simulated}` | During PyClaw simulation |
| `coarse_frame` | `{time, wave_heights}` (compressed) | Each output timestep |
| `coarse_complete` | `{impacts}` | Coarse finished |
| `zones_suggested` | `{zones}` | After impact detection |
| `detail_progress` | `{zone_id, percent}` | During Boussinesq |
| `detail_complete` | `{zone_id, summary}` | Zone finished |
| `error` | `{message}` | On failure |

## Frontend

Three-panel layout:
- **Left sidebar** — earthquake config (simple/advanced), simulation controls, focus zone management
- **Center** — map (2D MapLibre) or globe (3D CesiumJS) with interactive placement, wave animation, drawing tools
- **Bottom** — collapsible timeline of arrivals + result visualization tabs
- **Top bar** — 2D/3D toggle, export menu

### Visualization Layers
- Wave height heatmap (animated, Deck.gl)
- Arrival time contours
- Max wave height markers
- Inundation extent polygon
- Flood depth color ramp
- Flow velocity overlay

## Technology Stack

### Backend (Python)

| Library | Purpose |
|---------|---------|
| FastAPI + Uvicorn | Web framework and ASGI server |
| **clawpack (PyClaw)** | **SWE solver with Roe Riemann solver** |
| Celery + Redis | Task queue for background Boussinesq jobs |
| NumPy, SciPy | Numerical computation, Boussinesq solver |
| xarray + netCDF4 | Bathymetry data, simulation output |
| rasterio | GeoTIFF read/write |
| shapely, pyproj | Geometry and coordinate transforms |
| SQLAlchemy + SQLite | Simulation metadata |
| pytest | Testing |

### Frontend (TypeScript)

| Library | Purpose |
|---------|---------|
| React + Vite | UI framework and build |
| MapLibre GL JS | 2D map |
| CesiumJS | 3D globe |
| Zustand | State management |
| Tailwind CSS | Styling |
| D3.js | Charts and timeline |
| MapLibre Draw | Polygon drawing |
| Deck.gl | Heatmap and data viz |
| FileSaver.js | Client-side export |
| Vitest | Testing |

## Project Structure

```
tsunami/
├── docker-compose.yml
├── CLAUDE.md
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/tsunami/
│       ├── api/
│       │   ├── routes/              # REST endpoints
│       │   ├── websocket.py         # WebSocket handler
│       │   └── deps.py              # Dependencies
│       ├── simulation/
│       │   ├── okada.py             # Earthquake → displacement
│       │   ├── swe_solver.py        # PyClaw wrapper for coarse SWE
│       │   ├── boussinesq.py        # Custom Boussinesq (fine)
│       │   ├── inundation.py        # Flood mapping
│       │   ├── impact.py            # Coastal impact detection
│       │   └── grid.py              # Grid management
│       ├── bathymetry/
│       │   ├── gebco.py             # GEBCO fetcher/cache
│       │   ├── etopo.py             # ETOPO fetcher/cache
│       │   ├── procedural.py        # Fallback generator
│       │   └── service.py           # Unified interface
│       ├── models/                  # SQLAlchemy models
│       ├── schemas/                 # Pydantic schemas
│       ├── workers/
│       │   ├── celery_app.py
│       │   └── tasks.py
│       └── config.py
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── components/
│       │   ├── MapView/
│       │   ├── GlobeView/
│       │   ├── ControlPanel/
│       │   ├── Timeline/
│       │   └── common/
│       ├── stores/
│       ├── services/
│       ├── types/
│       └── utils/
├── data/
│   ├── gebco/
│   ├── etopo/
│   └── presets/
└── docs/
```

## Key Design Decision: PyClaw vs Custom SWE Solver

### Why PyClaw

| Aspect | Custom Lax-Friedrichs (v1) | PyClaw (v2) |
|--------|---------------------------|-------------|
| Accuracy | First-order, diffusive | Second-order with MC limiter |
| Riemann solver | None (central flux) | Roe with entropy fix |
| Bathymetry | Manual source terms | Native via augmented solver |
| Dry states | Simple threshold | Proper wet/dry interface |
| Validation | Needs custom tests | Published benchmarks |
| Maintenance | Custom code to maintain | Community-maintained |

### What we keep custom
- **Boussinesq solver** — PyClaw doesn't provide dispersive wave physics
- **Okada model** — earthquake source is domain-specific
- **Grid management** — our Grid class bridges lat/lon ↔ PyClaw domains
- **Impact detection** — custom coastal analysis logic
- **Inundation mapping** — flood extent extraction from results

### PyClaw integration pattern

The `swe_solver.py` module becomes a **wrapper** around PyClaw:

```python
def run_swe(grid: Grid, displacement: np.ndarray, config: SWESolverConfig,
            frame_callback=None) -> SWEState:
    """Run coarse SWE using PyClaw."""
    # 1. Convert Grid → PyClaw Domain
    # 2. Set initial conditions from Okada displacement
    # 3. Set bathymetry as auxiliary variable
    # 4. Configure solver (Roe, MC limiter, BCs)
    # 5. Run Controller with frame callbacks
    # 6. Convert results back to SWEState
```

The external interface (`run_swe`, `SWEState`, `SWESolverConfig`) stays the same — the rest of the system doesn't need to know PyClaw is under the hood.

## Testing Strategy

- **SWE solver** — validate PyClaw wrapper against analytical dam-break solution
- **Boussinesq solver** — validate against plane beach runup benchmark
- **Okada model** — compare against published displacement values
- **API integration** — full simulation lifecycle via REST endpoints
- **Frontend** — Vitest for component logic
- **End-to-end** — earthquake through inundation pipeline test

## Changes from v1

1. **SWE solver**: Custom Lax-Friedrichs → PyClaw with Roe Riemann solver
2. **Boundary conditions**: Reflective only → Reflective (land) + Extrapolation (open ocean)
3. **Dependencies**: Added `clawpack` to backend requirements
4. **Solver accuracy**: First-order → second-order with wave limiters
5. **Bathymetry handling in SWE**: Manual source terms → native via PyClaw auxiliary variables
6. **Solver config**: Added `limiter`, `bc_type` fields
