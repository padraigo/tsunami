# Tsunami Simulator — Product Requirements Document

## 1. Product Vision

A web-based tsunami simulation platform that enables researchers and educators to model earthquake-generated tsunamis from source to impact. Users define an earthquake, watch wave propagation across ocean basins in real-time, identify threatened coastlines, and run high-fidelity local impact analysis on selected areas.

The system uses a two-level simulation approach: coarse propagation across ocean basins using a well-balanced finite volume solver, followed by fine-scale Boussinesq modeling for nearshore impact and inundation analysis.

## 2. User Personas

### Researcher
- Seismologist or coastal engineer studying tsunami propagation and impact
- Needs physically accurate simulations with configurable fault parameters
- Exports results (GeoJSON, NetCDF, CSV) for use in GIS tools or further analysis
- Wants full control over simulation parameters (fault geometry, grid resolution, solver settings)

### Educator
- University instructor teaching geophysics, oceanography, or disaster science
- Uses the simulator for classroom demonstrations and student exercises
- Needs intuitive UI with sensible defaults (simple earthquake input mode)
- Values clear visualization over parameter complexity

### Emergency Planner
- Municipal or regional disaster preparedness professional
- Interested in inundation mapping for specific coastal areas
- Uses preset coastal locations and focus zones
- Needs exportable flood maps for integration with evacuation planning

## 3. Functional Requirements

### FR-1: Earthquake Source Definition

| ID | Requirement | Priority |
|----|------------|----------|
| FR-1.1 | Simple mode: user specifies lat/lon, magnitude (Mw), and wave direction | Must |
| FR-1.2 | Advanced mode: user specifies full Okada fault parameters (strike, dip, rake, slip, length, width, depth) | Must |
| FR-1.3 | Click-to-place earthquake epicenter on map | Must |
| FR-1.4 | System auto-derives fault geometry from magnitude using Wells & Coppersmith (1994) scaling in simple mode | Must |
| FR-1.5 | Simulation domain automatically sized based on earthquake magnitude | Must |

### FR-2: Coarse Wave Propagation

| ID | Requirement | Priority |
|----|------------|----------|
| FR-2.1 | Solve shallow water equations using a well-balanced Lax-Friedrichs finite volume scheme with stability guards | Must |
| FR-2.2 | Support configurable grid resolution (default ~2 km for coarse) | Must |
| FR-2.3 | Use GEBCO 2025 bathymetry as primary data source; procedural bathymetry as offline/demo fallback | Must |
| FR-2.3a | Mask inland water bodies (lakes, rivers) to prevent spurious inundation in coarse propagation | Should |
| FR-2.4 | Stream wave height frames to frontend via WebSocket for live animation | Must |
| FR-2.5 | Complete coarse simulation in seconds to a few minutes (interactive speed) | Must |
| FR-2.6 | Produce maximum wave height map and arrival time map | Must |
| FR-2.7 | Support Manning friction for realistic energy dissipation | Should |
| FR-2.8 | Handle spherical geometry correctly for basin-scale simulations | Should |

### FR-3: Impact Detection & Focus Zones

| ID | Requirement | Priority |
|----|------------|----------|
| FR-3.1 | Automatically detect coastline segments with significant wave heights | Must |
| FR-3.2 | Cluster impact points into suggested focus zones | Must |
| FR-3.3 | User can accept auto-detected zones | Must |
| FR-3.4 | User can draw custom polygon zones on map | Must |
| FR-3.5 | User can select from preset coastal locations | Must |
| FR-3.6 | Configurable grid resolution per focus zone (default ~100 m) | Must |

### FR-4: Detailed Local Analysis

| ID | Requirement | Priority |
|----|------------|----------|
| FR-4.1 | Run Boussinesq solver with dispersive corrections for nearshore modeling | Must |
| FR-4.2 | Use boundary conditions from coarse simulation (one-way nesting) | Must |
| FR-4.3 | Execute as background jobs (Celery workers) | Must |
| FR-4.4 | Stream progress to frontend via WebSocket | Must |
| FR-4.5 | Compute inundation extent (how far inland water goes) | Must |
| FR-4.6 | Compute flood depth map on land | Must |
| FR-4.7 | Compute flow velocity map | Must |
| FR-4.8 | Compute maximum runup height | Must |
| FR-4.9 | Auto-create up to 3 coastal focus zones from impact detection results (automatic refinement) | Should |
| FR-4.10 | Run automatic Boussinesq refinement at ~5 km resolution with boundary conditions taken from the coarse solution | Should |

### FR-5: Visualization

| ID | Requirement | Priority |
|----|------------|----------|
| FR-5.1 | 2D map view (MapLibre GL) with wave animation overlay | Must |
| FR-5.2 | 3D globe view (CesiumJS) with terrain and wave visualization | Deferred (future release) |
| FR-5.3 | Toggle between 2D and 3D views, preserving state | Deferred (future release) |
| FR-5.4 | Wave height heatmap animation (Deck.gl) | Deferred (future release) |
| FR-5.5 | Arrival time contour overlay | Must |
| FR-5.6 | Inundation extent polygon overlay | Must |
| FR-5.7 | Flood depth color-ramped overlay | Must |
| FR-5.8 | Timeline panel showing wave arrival events | Must |
| FR-5.9 | Animation playback controls (play, pause, speed, scrub) | Should |
| FR-5.10 | Map-click epicenter placement: first click sets location, second click sets wave direction and magnitude (two-click gesture) | Must |
| FR-5.11 | Timeline slider for scrubbing wave propagation playback | Must |
| FR-5.12 | Progress bar displayed on frontend during active simulation | Must |

### FR-6: Data Export

| ID | Requirement | Priority |
|----|------------|----------|
| FR-6.1 | Export inundation extent as GeoJSON | Must |
| FR-6.2 | Export tabular impact data as CSV | Must |
| FR-6.3 | Export wave height time series as NetCDF | Must |
| FR-6.4 | Export spatial maps as GeoTIFF | Should |

### FR-7: Simulation Management

| ID | Requirement | Priority |
|----|------------|----------|
| FR-7.1 | Create, list, view, and delete simulations | Must |
| FR-7.2 | Persist simulation results for later retrieval | Must |
| FR-7.3 | Name simulations for easy identification | Should |

### FR-8: Tidal Modeling

| ID | Requirement | Priority |
|----|------------|----------|
| FR-8.1 | User can set earthquake date/time (UTC); system includes tidal offset in initial sea-surface conditions | Should |
| FR-8.2 | Global tidal visualization mode showing the ~25-hour tidal cycle using a 4-constituent harmonic model (M2, S2, K1, O1) | Should |
| FR-8.3 | Tide height visualization uses a diverging blue/red color ramp (negative = below MSSL, positive = above) | Should |

### FR-9: Developer Integration (MCP)

| ID | Requirement | Priority |
|----|------------|----------|
| FR-9.1 | MCP server exposes simulation tools for Claude Code: health, list, create, run, results, presets | Should |
| FR-9.2 | MCP server uses stdio transport with configurable backend URL | Should |

## 4. Non-Functional Requirements

### NFR-1: Performance

| ID | Requirement | Target |
|----|------------|--------|
| NFR-1.1 | Coarse SWE simulation (2 km grid, 6hr simulated) | < 2 minutes wall time |
| NFR-1.2 | Detailed Boussinesq simulation (100 m grid, typical focus zone) | < 15 minutes wall time |
| NFR-1.3 | Frontend remains responsive during simulation | Always |
| NFR-1.4 | Wave animation frame rate | >= 10 fps |

### NFR-2: Accuracy

| ID | Requirement | Target |
|----|------------|--------|
| NFR-2.1 | SWE solver validated against analytical solutions | Required |
| NFR-2.2 | Okada model validated against published displacement values | Required |
| NFR-2.3 | Coarse propagation uses well-balanced Lax-Friedrichs finite volume scheme with stability guards | Required |
| NFR-2.4 | Boussinesq solver includes dispersive corrections | Required |

### NFR-3: Deployment

| ID | Requirement | Target |
|----|------------|--------|
| NFR-3.1 | Fully containerized via Docker Compose | Required |
| NFR-3.2 | Single `docker-compose up` to start all services | Required |
| NFR-3.3 | Works on Linux, macOS (Docker Desktop) | Required |
| NFR-3.4 | No external service dependencies beyond Docker | Required |

### NFR-4: Usability

| ID | Requirement | Target |
|----|------------|--------|
| NFR-4.1 | Simple mode usable without seismology knowledge | Required |
| NFR-4.2 | No data download required for basic demo (procedural bathymetry) | Required |
| NFR-4.3 | Real bathymetry auto-downloaded and cached on first use | Required |

## 5. Out of Scope (v1)

- Real-time earthquake data feeds (USGS, etc.)
- Multi-source tsunami modeling (multiple simultaneous earthquakes)
- Landslide-generated tsunamis
- Atmospheric pressure-driven tsunamis (meteotsunamis)
- User authentication or multi-tenancy
- Mobile-optimized UI
- Operational tsunami warning system integration

## 6. Success Criteria

1. A user can place an M8.0 earthquake in the Indian Ocean, watch wave propagation animate across the basin, and see impact predictions on the coast of Sumatra — all within 5 minutes of starting the application.

2. A researcher can configure a full Okada fault model, run a coarse simulation, select focus zones, run detailed Boussinesq analysis, and export inundation maps as GeoJSON — in a single workflow without leaving the application.

3. Solver outputs match published benchmark solutions (analytical dam-break, plane beach runup) within acceptable numerical tolerances.

4. The system runs entirely from `docker-compose up` with no external dependencies.
