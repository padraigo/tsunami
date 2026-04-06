# Tsunami Simulator — Design Specification

## Overview

A web-based tsunami simulation system that models earthquake-generated tsunamis using a two-level approach: coarse Shallow Water Equation (SWE) propagation across ocean basins for interactive exploration, followed by high-fidelity Boussinesq modeling for detailed local impact analysis. Serves both educational/visualization and research/scientific use cases.

## Architecture

### System Components

- **FastAPI Server** — serves frontend, REST API, WebSocket for live progress, runs coarse SWE simulations in-process
- **Redis** — lightweight job queue for dispatching high-fidelity analysis jobs
- **Celery Worker(s)** — run Boussinesq solver and inundation mapping as background jobs; independently scalable
- **Bathymetry Data Service** — fetches, caches, and serves GEBCO/ETOPO ocean/terrain data at multiple resolutions, with procedural fallback
- **Data Store** — simulation results as NetCDF (time series) and GeoTIFF (spatial maps); metadata in SQLite via SQLAlchemy
- **Frontend** — React/TypeScript SPA with MapLibre GL (2D), CesiumJS (3D), and interactive control panel

### Deployment

Docker Compose with four services:

| Service | Role | Scaling |
|---------|------|---------|
| `backend` | FastAPI + coarse SWE solver | Single instance |
| `worker` | Celery worker for Boussinesq jobs | Horizontal (replicas) |
| `redis` | Job queue + result backend | Single instance |
| `frontend` | React dev server / nginx (prod) | Single instance |

All services share a `./data` volume for bathymetry cache and simulation results.

## Simulation Pipeline

### Step 1: Earthquake Source Definition

Two input modes:

**Simple mode** — user provides:
- Latitude, longitude (click on map or type)
- Magnitude (Mw)
- Direction (azimuth in degrees)

The system derives fault geometry (length, width, depth, dip, strike, slip) using Wells & Coppersmith (1994) empirical scaling laws.

**Advanced mode** — user provides full Okada model parameters:
- Strike, dip, rake (degrees)
- Slip (meters)
- Fault length, width (km)
- Depth (km)

### Step 2: Okada Model — Seafloor Displacement

Converts fault parameters into a 2D seafloor displacement field using the Okada (1985) analytical solution. This displacement serves as the initial condition for wave propagation — the sea surface is assumed to instantaneously match the seafloor deformation.

### Simulation Domain

The coarse simulation domain is automatically determined from the earthquake location and magnitude. Larger earthquakes get larger domains (e.g., M8.0+ covers a full ocean basin, M7.0 covers ~1000 km radius). The user can manually adjust the domain bounds if needed.

### Step 3: Coarse Bathymetry Fetch

Retrieves ocean depth data for the simulation domain:
- **Primary**: GEBCO global grid (~450m native, resampled to ~1–5 km for coarse simulation)
- **Fallback**: Procedural generation (continental shelf profiles, idealized basins) when real data isn't available or for quick demos

Data is cached locally after first fetch. Grid managed via xarray.

### Step 4: SWE Solver (Coarse, In-Process)

Solves the nonlinear Shallow Water Equations on a ~1–5 km grid using a finite volume method (NumPy-based):

- Time step auto-calculated from CFL condition
- Configurable simulation duration (default 6 hours)
- Results streamed to frontend via WebSocket as compressed frames for live wave animation
- Runs in-process on the FastAPI server — expected to complete in seconds to a couple minutes

**Outputs:**
- Wave height field time series (NetCDF)
- Maximum wave height map (GeoTIFF)
- Wave arrival time map (GeoTIFF)
- Coastline impact list (locations with max wave height and arrival time)

### Step 5: Impact Detection

Scans coastal grid cells for wave heights above a configurable threshold. Clusters nearby impact points into suggested focus zones using spatial clustering. These suggestions are pushed to the frontend via WebSocket.

### Step 6: Focus Zone Selection

User selects areas for detailed analysis via three methods (all selectable):

1. **Auto-detected zones** — accept system suggestions from Step 5
2. **Preset locations** — pick from a curated list of known coastal cities/regions
3. **Custom drawing** — draw polygons directly on the map using drawing tools

Each zone has a configurable grid resolution (default ~100m).

### Step 7: High-Resolution Bathymetry Fetch

For each focus zone, fetches fine-resolution data:
- **Primary**: ETOPO or higher-resolution regional datasets (~50–100m cells)
- **Fallback**: Interpolated GEBCO data or procedural profiles

### Step 8: Boussinesq Solver (Fine, Background Worker)

Dispatched as a Celery background job. Solves Boussinesq equations on the fine grid using boundary conditions extracted from the coarse SWE simulation (one-way nesting — fine does not feed back into coarse).

- Progress streamed to frontend via WebSocket
- Expected runtime: minutes to tens of minutes depending on zone size and resolution

**Outputs per focus zone:**
- Inundation extent (GeoJSON polygon)
- Flood depth map (GeoTIFF)
- Flow velocity map (GeoTIFF)
- Maximum runup height (scalar)
- Event timeline (time-stamped wave height at key points)

## Data Model

### Core Entities

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
│   ├── time_step_seconds: float (auto from CFL)
│   └── bathymetry_source: "gebco" | "procedural"
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
| `POST` | `/api/simulations/{id}/run-coarse` | Start coarse SWE simulation |
| `GET` | `/api/simulations/{id}/coarse-result` | Get coarse results (metadata + download URLs) |
| `POST` | `/api/simulations/{id}/focus-zones` | Add focus zone (GeoJSON body) |
| `GET` | `/api/simulations/{id}/focus-zones` | List focus zones |
| `PUT` | `/api/simulations/{id}/focus-zones/{zid}` | Update zone |
| `DELETE` | `/api/simulations/{id}/focus-zones/{zid}` | Remove zone |
| `POST` | `/api/simulations/{id}/run-detail` | Start detailed analysis (all zones) |
| `POST` | `/api/simulations/{id}/focus-zones/{zid}/run` | Start single zone analysis |
| `GET` | `/api/simulations/{id}/focus-zones/{zid}/result` | Get detail results |
| `GET` | `/api/simulations/{id}/export?format=geojson\|csv\|netcdf` | Export results |
| `GET` | `/api/bathymetry/check?bounds=...` | Check data availability for region |
| `POST` | `/api/bathymetry/fetch` | Trigger download for region |
| `GET` | `/api/presets/locations` | List preset coastal locations |

## WebSocket Protocol

Connect to `WS /api/ws/simulations/{id}`.

Server-to-client messages:

| Type | Payload | When |
|------|---------|------|
| `coarse_progress` | `{step, total, time_simulated}` | During coarse simulation |
| `coarse_frame` | `{time, wave_heights}` (compressed grid) | Each output timestep — for live animation |
| `coarse_complete` | `{impacts: [{lat, lon, max_height}, ...]}` | Coarse simulation finished |
| `zones_suggested` | `{zones: [FocusZone, ...]}` | After impact detection |
| `detail_progress` | `{zone_id, percent}` | During detailed analysis |
| `detail_complete` | `{zone_id, summary}` | Zone analysis finished |
| `error` | `{message}` | On failure |

## Frontend

### Layout

Three-panel layout:
- **Left sidebar** — earthquake source config (simple/advanced toggle), simulation controls, focus zone management with progress indicators
- **Center** — map (2D) or globe (3D) view with interactive earthquake placement, wave animation overlay, and polygon drawing tools
- **Bottom panel** — collapsible timeline of wave arrivals and result visualization tabs (arrival map, max heights, animation playback)
- **Top bar** — 2D/3D view toggle, export dropdown menu

### View Toggle

Toggle between 2D (MapLibre GL) and 3D (CesiumJS) views. Both share the same data layers — switching views preserves the current simulation state and overlays.

### Interaction Flow

1. Click map to place earthquake epicenter (or type coordinates in sidebar)
2. Adjust magnitude, direction, and other parameters
3. Click "Run Coarse" — wave propagation animates on map in real-time via WebSocket frames
4. System highlights impact zones on coastline; user accepts, modifies, or draws custom focus zones
5. Click "Run Detailed" — progress bar shows background job status per zone
6. Results render as overlays (inundation extent, flood depth heatmap) and populate the timeline
7. Switch to 3D for presentation view; export data via menu

### Visualization Layers

- **Wave height heatmap** — animated Deck.gl layer showing wave propagation over time
- **Arrival time contours** — isolines on the map showing when waves reach each point
- **Max wave height** — color-coded coastal markers or heatmap
- **Inundation extent** — shaded polygon overlay on land areas
- **Flood depth** — color-ramped raster overlay within inundation zones
- **Flow velocity** — vector field or color-coded overlay

## Technology Stack

### Backend (Python)

| Library | Purpose |
|---------|---------|
| FastAPI + Uvicorn | Web framework and ASGI server |
| Celery + Redis | Task queue for background Boussinesq jobs |
| NumPy, SciPy | Core numerical computation for solvers |
| xarray + netCDF4 | Bathymetry data loading and grid management |
| rasterio | GeoTIFF read/write |
| shapely, pyproj | Geometry operations and coordinate transforms |
| SQLAlchemy + SQLite | Simulation metadata storage |
| pytest | Testing |

### Frontend (TypeScript)

| Library | Purpose |
|---------|---------|
| React + Vite | UI framework and build tool |
| MapLibre GL JS | 2D map rendering |
| CesiumJS | 3D globe rendering |
| Zustand | State management |
| Tailwind CSS | Styling |
| D3.js | Charts and timeline visualization |
| MapLibre Draw | Polygon drawing tools for focus zones |
| Deck.gl | High-performance heatmap and data visualization layers |
| FileSaver.js | Client-side file export |
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
│       │   ├── routes/              # REST endpoint modules
│       │   ├── websocket.py         # WebSocket handler
│       │   └── deps.py              # Dependency injection
│       ├── simulation/
│       │   ├── okada.py             # Earthquake → seafloor displacement
│       │   ├── swe_solver.py        # Shallow Water Equations (coarse)
│       │   ├── boussinesq.py        # Boussinesq solver (fine)
│       │   ├── inundation.py        # Flood extent mapping
│       │   └── grid.py              # Grid management, interpolation
│       ├── bathymetry/
│       │   ├── gebco.py             # GEBCO data fetcher/cache
│       │   ├── etopo.py             # ETOPO data fetcher/cache
│       │   ├── procedural.py        # Fallback generator
│       │   └── service.py           # Unified bathymetry interface
│       ├── models/                  # SQLAlchemy models
│       ├── schemas/                 # Pydantic request/response schemas
│       ├── workers/
│       │   ├── celery_app.py        # Celery application config
│       │   └── tasks.py             # Background task definitions
│       └── config.py                # Application configuration
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── components/
│       │   ├── MapView/             # MapLibre 2D map
│       │   ├── GlobeView/           # CesiumJS 3D globe
│       │   ├── ControlPanel/        # Left sidebar controls
│       │   ├── Timeline/            # Bottom results panel
│       │   └── common/              # Shared UI components
│       ├── stores/                  # Zustand state stores
│       ├── services/                # API client, WebSocket manager
│       ├── types/                   # TypeScript type definitions
│       └── utils/                   # Helper functions
├── data/
│   ├── gebco/                       # Cached GEBCO tiles
│   ├── etopo/                       # Cached ETOPO tiles
│   └── presets/                     # Preset coastal location configs
└── docs/
    └── superpowers/specs/           # Design documents
```

## Testing Strategy

- **Solver unit tests** — validate SWE and Boussinesq solvers against known analytical solutions (e.g., wave propagation over flat bottom, runup on a plane beach)
- **Okada model tests** — compare displacement output against published values
- **API integration tests** — full simulation lifecycle via REST endpoints
- **Frontend component tests** — Vitest for UI logic, map interactions
- **End-to-end** — run a small simulation through the full pipeline and verify outputs

## Export Formats

| Format | Content |
|--------|---------|
| GeoJSON | Inundation extent polygons, coastline impact points, focus zone boundaries |
| CSV | Tabular impact data (location, max height, arrival time, runup) |
| NetCDF | Full wave height time series grids, flood depth grids |
| GeoTIFF | Max wave heights, arrival times, flood depth, flow velocity as georeferenced rasters |
