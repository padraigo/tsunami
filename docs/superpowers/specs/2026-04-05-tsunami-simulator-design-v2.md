# Tsunami Simulator — Design Specification v2

> Supersedes v1. Key change: Custom well-balanced Lax-Friedrichs SWE solver (active) replaces PyClaw/GeoClaw for coarse propagation. Custom Boussinesq solver retained for fine-scale nearshore modeling.

## Overview

A web-based tsunami simulation system using a two-level approach:
1. **Coarse propagation** — Custom well-balanced Lax-Friedrichs solver with perturbation pressure formulation on a ~2–5 km grid. Well-balanced via perturbation formulation, 2D unsplit stability fix, NaN guards, and stability clamps. Runs in-process for interactive speed.
2. **Fine-scale nearshore** — Custom Boussinesq solver with dispersive corrections on a ~100 m grid. Background worker job for detailed inundation analysis.

Serves educational/visualization and research/scientific use cases.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Web Frontend                           │
│  ┌──────────────┐  ┌──────────────────────────────────────┐  │
│  │  2D Map View  │  │  Control Panel                       │  │
│  │  (MapLibre)   │  │  - Earthquake source (click-to-place)│  │
│  │  - Wave anim  │  │  - Timeline slider                   │  │
│  │  - Tidal mode │  │  - Tidal mode toggle                 │  │
│  │  - Markers    │  │  - Progress bar                      │  │
│  └──────────────┘  └──────────────────────────────────────┘  │
│                         │ REST                               │
└─────────────────────────┼───────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────┐
│                    Docker Compose                            │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │              FastAPI Server (port 8001)              │    │
│  │  ┌────────────┐ ┌────────────┐ ┌─────────────────┐  │    │
│  │  │ REST API   │ │ Tides API  │ │ Custom SWE      │  │    │
│  │  │ /sims      │ │ /tides     │ │ Solver          │  │    │
│  │  │ /presets   │ │ /health    │ │ (in-process)    │  │    │
│  │  └────────────┘ └────────────┘ └─────────────────┘  │    │
│  └─────────────────────┬───────────────────────────────┘    │
│                         │ Job Queue                          │
│  ┌──────────┐   ┌──────▼───────────────────────────────┐    │
│  │  Redis   │◄──│         Worker Process(es)            │    │
│  │  (6380)  │   │  ┌─────────────────────────────────┐  │    │
│  └──────────┘   │  │  Boussinesq Solver (custom)     │  │    │
│                  │  │  + Inundation Mapper            │  │    │
│  ┌──────────┐   │  └─────────────────────────────────┘  │    │
│  │ SQLite   │   └──────────────────────────────────────┘    │
│  │ + Files  │                                                │
│  └──────────┘   ┌──────────────────────────────────────┐    │
│                  │        Bathymetry Data Service        │    │
│                  │  GEBCO 2025 (primary) + procedural    │    │
│                  └──────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Docker Compose Services

| Service | Port | Role | Scaling |
|---------|------|------|---------|
| `backend` | 8001 | FastAPI + custom SWE solver (in-process) | Single |
| `worker` | — | Celery worker for Boussinesq jobs | Horizontal |
| `redis` | 6380 | Job queue + result backend | Single |
| `frontend` | 3000 | React dev server / nginx (prod) | Single |

**GEBCO bind-mount:** The GEBCO NetCDF file is mounted into the backend container. Set `TSUNAMI_DATA_DIR` to the host directory containing `GEBCO_2025_sub_ice.nc`.

```yaml
volumes:
  - ${TSUNAMI_DATA_DIR:-./backend/data}:/app/data
```

## Simulation Pipeline

### Step 1: Earthquake Source Definition

**Simple mode** — lat/lon, magnitude, direction. System derives fault geometry via Wells & Coppersmith (1994).

**Advanced mode** — full Okada parameters: strike, dip, rake, slip, length, width, depth.

An optional `earthquake_datetime` field enables tide-tsunami interaction: the tidal phase at the earthquake moment is added to the initial wave height field.

### Step 2: Okada Model — Seafloor Displacement

Okada (1985) analytical solution converts fault parameters into a 2D seafloor displacement field. This becomes the initial condition for wave propagation.

### Step 3: Simulation Domain

Domain automatically sized from earthquake magnitude (M7 → ~1000 km radius, M9 → full ocean basin). User can manually adjust.

### Step 4: Coarse Bathymetry Fetch

- **Primary**: GEBCO 2025 sub-ice topo/bathy global grid (~450 m native, resampled to ~1–5 km). Auto-detected from `TSUNAMI_DATA_DIR` at startup.
- **Inland masking**: Flood-fill algorithm (`scipy.ndimage`) identifies and masks inland water bodies (lakes, enclosed seas) from the ocean domain.
- **Fallback**: Procedural generation (continental shelf profiles) when GEBCO file is absent.
- Data cached locally after first use.

### Step 5: Custom SWE Solver (Coarse, In-Process)

**The active implementation.** A custom well-balanced Lax-Friedrichs scheme using a perturbation pressure formulation:

```python
from tsunami.simulation.swe_solver import run_swe, SWESolverConfig

config = SWESolverConfig(
    duration_seconds=6 * 3600,
    output_interval_seconds=300.0,
    cfl=0.4,
)

swe_state = run_swe(
    grid=grid,                  # Grid object with depth field
    displacement=displacement,  # Okada output (ny, nx) array
    config=config,
    frame_callback=on_frame,    # Called at each output interval
)
```

**Key design features:**

- **Well-balanced perturbation formulation** — solves for surface elevation perturbation `η` rather than total depth; bathymetry source terms cancel analytically at rest, preserving the lake-at-rest condition.
- **2D unsplit stability fix** — Lax-Friedrichs stability coefficient `α = 0.5 * dx / dt` applied separately in x and y, eliminating the corner-flow instability that appears in naive 2D splitting.
- **Stability clamps** — total water depth `H = max(h + η, 0)` and momentum zeroed where `H < MIN_DEPTH`. Prevents runaway values at wet/dry interfaces.
- **NaN guards** — every flux computation checks for NaN/Inf and resets affected cells to zero rather than propagating corruption through the domain.

**Boundary conditions:**
- Wall (reflective) for land boundaries
- Extrapolation (absorbing) for open ocean edges — eliminates artificial edge reflections

**Outputs:**
- Wave height field time series (NumPy arrays, saved as NetCDF)
- Maximum wave height map
- Wave arrival time map
- Coastline impact list

### Step 6: Impact Detection

Scans coastal cells for wave heights above threshold. Clusters into suggested focus zones via spatial clustering. Suggestions available via REST API.

### Step 7: Focus Zone Selection

Three methods (all available):
1. Accept auto-detected zones (top 3 by wave height)
2. Pick from preset coastal locations
3. Draw custom polygons on map

### Step 8: High-Resolution Bathymetry Fetch

ETOPO or higher-res regional data (~50–100 m) for focus zones. Fallback to interpolated GEBCO or procedural.

### Step 9: Boussinesq Solver (Fine, Background Worker)

Custom solver using operator splitting: SWE step + dispersive Peregrine correction. One-way nesting — boundary conditions extracted from coarse SWE frames (saved as NPZ) and applied at zone boundaries.

**Outputs per focus zone:**
- Inundation extent (GeoJSON)
- Flood depth map (GeoTIFF)
- Flow velocity map (GeoTIFF)
- Maximum runup height
- Event timeline

### Step 10: Tidal Modeling

A 4-constituent harmonic tidal model provides global tidal animation and optionally modulates the initial tsunami condition.

**Constituents:** M2 (principal lunar semidiurnal), S2 (principal solar semidiurnal), K1 (lunisolar diurnal), O1 (principal lunar diurnal).

**API endpoint:**
```
POST /api/tides/compute
```
Request body includes bounding box, grid resolution, time range, and optional `earthquake_datetime` for tidal phase lock. Returns a `FramesResponse` (same format as coarse SWE frames) containing tidal height fields at each timestep.

**Frontend tidal mode:**
- Activated via toggle in the control panel
- Uses a diverging blue/red color palette (positive = flood tide, negative = ebb tide)
- Animated via `ImageSource` raster replacement in MapLibre GL JS
- Can be overlaid with or subtracted from the tsunami wave animation

### Step 11: Auto Coastal Refinement

After the coarse SWE run completes, the system automatically identifies the top 3 impact zones and dispatches Boussinesq detail runs without requiring user interaction.

**Workflow:**
1. Coarse run completes; impact detection ranks coastal cells by maximum wave height.
2. Top 3 clusters are selected as detail zones.
3. Coarse frames are saved as compressed NPZ files in `{sim_dir}/coarse_frames/` for boundary condition extraction.
4. A Boussinesq job is queued per zone at 5 km resolution (configurable) with one-way nesting from the coarse NPZ frames.
5. Results are available at:

```
GET /api/simulations/{uid}/detail-results
```

Response includes per-zone inundation extent, flood depth, max runup, and zone metadata.

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
│   ├── earthquake_datetime: datetime (optional, for tide-tsunami interaction)
│   └── FaultParams (advanced mode, nullable)
│       ├── strike, dip, rake: float (degrees)
│       ├── slip: float (meters)
│       └── length, width: float (km)
│
├── CoarseConfig
│   ├── grid_resolution_km: float (default 2.0)
│   ├── duration_hours: float (default 6.0)
│   ├── bathymetry_source: "gebco" | "procedural"
│   └── solver_settings: {cfl, manning_n}
│
├── CoarseResult
│   ├── wave_height_field: path to NetCDF
│   ├── coarse_frames_dir: path to NPZ directory (for BC extraction)
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
│   ├── grid_resolution_m: float (default 5000)
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
| `GET` | `/api/simulations/{uid}` | Get simulation status & metadata |
| `DELETE` | `/api/simulations/{uid}` | Delete simulation and results |
| `POST` | `/api/simulations/{uid}/run-coarse` | Start coarse SWE + auto detail dispatch |
| `GET` | `/api/simulations/{uid}/frames` | Wave animation frames (FramesResponse) |
| `GET` | `/api/simulations/{uid}/coarse-result` | Get coarse result summary |
| `GET` | `/api/simulations/{uid}/detail-results` | Get detail zone results (all zones) |
| `POST` | `/api/simulations/{uid}/focus-zones` | Add focus zone |
| `GET` | `/api/simulations/{uid}/focus-zones` | List focus zones |
| `PUT` | `/api/simulations/{uid}/focus-zones/{zid}` | Update zone |
| `DELETE` | `/api/simulations/{uid}/focus-zones/{zid}` | Remove zone |
| `POST` | `/api/simulations/{uid}/run-detail` | Start detailed analysis (all zones) |
| `POST` | `/api/simulations/{uid}/focus-zones/{zid}/run` | Start single zone |
| `GET` | `/api/simulations/{uid}/focus-zones/{zid}/result` | Get detail results for zone |
| `GET` | `/api/simulations/{uid}/export?format=geojson\|csv\|netcdf` | Export |
| `POST` | `/api/tides/compute` | Global tidal animation (FramesResponse) |
| `GET` | `/api/bathymetry/check?bounds=...` | Check data availability |
| `POST` | `/api/bathymetry/fetch` | Trigger download |
| `GET` | `/api/presets/locations` | List preset locations |
| `GET` | `/api/health` | Health check |

## Frontend

Two-panel layout:
- **Left sidebar** — earthquake config (simple/advanced), simulation controls, focus zone management, tidal mode toggle
- **Center** — 2D map (MapLibre GL JS) with click-to-place epicenter, wave animation, impact markers, tidal overlay
- **Bottom** — timeline slider for wave animation scrubbing, progress bar during simulation
- **Top bar** — tidal mode toggle, export menu

**3D globe (CesiumJS):** deferred to a future milestone.

### Visualization Layers
- Wave height animation via `ImageSource` raster replacement (MapLibre GL JS)
- Tidal height animation (same mechanism, diverging blue/red palette)
- Arrival time contours
- Max wave height impact markers
- Inundation extent polygon
- Flood depth color ramp
- Flow velocity overlay

### Map Interaction
- **Click-to-place epicenter** — clicking the map sets earthquake lat/lon in the control panel
- **Timeline slider** — scrubs through animation frames; displays current simulated time
- **Progress bar** — shown during active simulation runs
- **Drawing tools** — polygon drawing for custom focus zones (MapLibre Draw)

## MCP Server

A stdio-transport MCP server wraps the REST API for Claude Code integration. Registered via `.claude/mcp.json`.

**Available tools:**

| Tool | Description |
|------|-------------|
| `tsunami_health` | Check backend health status |
| `tsunami_list_simulations` | List all simulations with status |
| `tsunami_create_simulation` | Create a new simulation from parameters |
| `tsunami_run_coarse` | Trigger coarse SWE run for a simulation |
| `tsunami_get_frames` | Retrieve wave animation frame data |
| `tsunami_get_detail_results` | Retrieve coastal refinement results |
| `tsunami_compute_tides` | Compute global tidal animation |

Registration:
```json
{
  "mcpServers": {
    "tsunami": {
      "command": "python",
      "args": ["-m", "tsunami.mcp.server"],
      "transport": "stdio"
    }
  }
}
```

## Technology Stack

### Backend (Python)

| Library | Purpose |
|---------|---------|
| FastAPI + Uvicorn | Web framework and ASGI server |
| **NumPy** | **Custom SWE solver core (Lax-Friedrichs, perturbation formulation)** |
| **scipy.ndimage** | **Inland water body masking (flood-fill)** |
| clawpack (PyClaw) | Installed, not yet used for SWE — custom solver active |
| Celery + Redis | Task queue for background Boussinesq jobs |
| SciPy | Boussinesq solver, interpolation |
| xarray + netCDF4 | Bathymetry data (GEBCO), simulation output |
| rasterio | GeoTIFF read/write |
| shapely, pyproj | Geometry and coordinate transforms |
| SQLAlchemy + SQLite | Simulation metadata |
| pytest | Testing |

### Frontend (TypeScript)

| Library | Purpose |
|---------|---------|
| React + Vite | UI framework and build |
| MapLibre GL JS | 2D map, wave animation (ImageSource), drawing tools |
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
│       │   └── deps.py              # Dependencies
│       ├── simulation/
│       │   ├── okada.py             # Earthquake → displacement
│       │   ├── swe_solver.py        # Custom Lax-Friedrichs SWE solver
│       │   ├── boussinesq.py        # Custom Boussinesq (fine)
│       │   ├── inundation.py        # Flood mapping
│       │   ├── impact.py            # Coastal impact detection
│       │   └── grid.py              # Grid management
│       ├── bathymetry/
│       │   ├── gebco.py             # GEBCO 2025 loader/cache
│       │   ├── procedural.py        # Fallback generator
│       │   └── service.py           # Unified interface
│       ├── tides/
│       │   └── harmonic.py          # M2/S2/K1/O1 tidal model
│       ├── mcp/
│       │   └── server.py            # MCP stdio server
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
│       │   ├── ControlPanel/
│       │   ├── Timeline/
│       │   └── common/
│       ├── stores/
│       ├── services/
│       ├── types/
│       └── utils/
├── data/
│   ├── bathymetry/
│   │   └── GEBCO_2025_sub_ice.nc    # Place here (not committed)
│   └── presets/
└── docs/
```

## Key Design Decision: Custom SWE Solver vs PyClaw

### Why the custom well-balanced solver

| Aspect | Custom Lax-Friedrichs v2 (active) | PyClaw (installed, not active) |
|--------|-----------------------------------|-------------------------------|
| Accuracy | First-order, well-balanced via perturbation formulation | Second-order with MC limiter |
| Bathymetry | Perturbation pressure; lake-at-rest satisfied analytically | Native via augmented solver |
| Dry states | Stability clamps + depth floor | Proper wet/dry interface |
| Stability | 2D unsplit α fix + NaN guards | CFL-limited, no special 2D fix needed |
| Dependencies | Pure NumPy, no compile step | Requires Fortran compiler + clawpack build |
| Integration | Direct Python, debuggable | Subprocess / Fortran callback |
| Validation | Custom tests against dam-break | Published benchmarks |
| Status | Active | Installed, deferred |

PyClaw remains an installation dependency and is the intended path for second-order accuracy, but the custom solver is active for all current simulations.

### What stays custom
- **Boussinesq solver** — PyClaw doesn't provide dispersive wave physics
- **Okada model** — earthquake source is domain-specific
- **Grid management** — our Grid class bridges lat/lon ↔ solver domains
- **Impact detection** — custom coastal analysis logic
- **Inundation mapping** — flood extent extraction from results

### SWE solver interface

The `swe_solver.py` module exposes a stable interface regardless of the underlying numerical scheme:

```python
def run_swe(grid: Grid, displacement: np.ndarray, config: SWESolverConfig,
            frame_callback=None) -> SWEState:
    """Run coarse SWE using well-balanced Lax-Friedrichs.

    Args:
        grid: Grid with bathymetry depth field
        displacement: Okada seafloor displacement (ny, nx), metres
        config: Solver configuration (duration, CFL, output interval)
        frame_callback: Optional callable(time_s, SWEState) for streaming

    Returns:
        Final SWEState with eta, hu, hv fields
    """
    # 1. Build initial condition from displacement
    # 2. Time-step loop with CFL-adaptive dt
    # 3. Lax-Friedrichs flux with perturbation formulation
    # 4. Apply stability clamps and NaN guards
    # 5. Call frame_callback at output intervals
    # 6. Return final SWEState
```

The external interface (`run_swe`, `SWEState`, `SWESolverConfig`) is stable — switching to PyClaw or another solver only requires changes inside this module.

## Testing Strategy

- **SWE solver** — validate against analytical dam-break solution; lake-at-rest conservation test
- **Boussinesq solver** — validate against plane beach runup benchmark
- **Okada model** — compare against published displacement values
- **API integration** — full simulation lifecycle via REST endpoints
- **Frontend** — Vitest for component logic
- **End-to-end** — earthquake through inundation pipeline test

## Changes from v1

1. **SWE solver**: Custom Lax-Friedrichs → well-balanced perturbation formulation with 2D unsplit stability fix, stability clamps, NaN guards (still custom, not PyClaw)
2. **Bathymetry**: GEBCO 2025 as primary source with inland water body masking via flood-fill
3. **Tidal modeling**: New 4-constituent harmonic model (M2, S2, K1, O1) with `POST /api/tides/compute`
4. **Auto coastal refinement**: Automatic top-3 zone detection, coarse NPZ BC extraction, Boussinesq at 5 km
5. **MCP server**: 7 tools wrapping REST API via stdio transport
6. **REST API**: New endpoints `/tides/compute`, `/simulations/{uid}/frames`, `/simulations/{uid}/detail-results`
7. **Frontend**: CesiumJS deferred; added click-to-place, timeline slider, tidal mode, progress bar, ImageSource animation
8. **Docker**: Ports 8001/3000/6380; GEBCO bind-mount via `TSUNAMI_DATA_DIR`
9. **Dependencies**: Added `scipy.ndimage`; clawpack installed but not active for SWE
