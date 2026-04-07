# Tsunami Simulator

Web-based tsunami simulation platform with real-time wave propagation visualization, GEBCO bathymetry, tidal modeling, and automatic coastal refinement.

## Features

- **Earthquake Source Modeling** — Okada (1985) analytical displacement from fault parameters or simplified magnitude/direction input
- **Wave Propagation** — 2D shallow water equations with well-balanced Lax-Friedrichs solver
- **Real Bathymetry** — GEBCO 2025 global ocean depth with inland water masking
- **Automatic Coastal Refinement** — Two-level nesting: coarse SWE → fine Boussinesq at detected impact zones
- **Tidal Modeling** — 4-constituent harmonic model (M2, S2, K1, O1) with global animation
- **Interactive Map** — MapLibre GL JS with click-to-place epicenter, wave animation, impact markers
- **MCP Integration** — Claude Code tools for simulation monitoring and control

## Quick Start

```bash
# Docker (recommended)
docker compose up -d
# Frontend: http://localhost:3000
# Backend API: http://localhost:8001

# Development
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
cd frontend && npm install && npm run dev
```

## Architecture

```
Frontend (React/MapLibre) → Nginx → FastAPI Backend → Redis → Celery Workers
                                       ↓
                              SQLite + GEBCO Data
```

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 3000 | React + MapLibre + Tailwind |
| Backend | 8001 | FastAPI + SWE solver |
| Redis | 6380 | Celery job queue |
| Worker | — | Boussinesq detail simulations |

## GEBCO Bathymetry

Download [GEBCO 2025 sub-ice topo/bathy](https://www.gebco.net/data-products/gridded-bathymetry-data) (NetCDF format) and place at:
```
backend/data/bathymetry/GEBCO_2025_sub_ice.nc
```
The system auto-detects and uses it. Without GEBCO, procedural bathymetry is used as fallback.

## Running Tests

```bash
# Backend (83 tests)
cd backend && source .venv/bin/activate && pytest tests/ -v

# Frontend (7 tests)
cd frontend && npx vitest run
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/simulations | Create simulation |
| GET | /api/simulations | List simulations |
| POST | /api/simulations/{uid}/run-coarse | Run coarse + auto detail |
| GET | /api/simulations/{uid}/frames | Wave animation frames |
| GET | /api/simulations/{uid}/detail-results | Detail zone results |
| POST | /api/tides/compute | Global tidal animation |
| GET | /api/presets/locations | Preset earthquakes |
| GET | /api/health | Health check |

## Tech Stack

**Backend:** Python 3.12, FastAPI, SQLAlchemy, Celery, Redis, NumPy, SciPy, xarray
**Frontend:** React 19, TypeScript, Vite, MapLibre GL JS, Zustand, Tailwind CSS
**Data:** GEBCO 2025 NetCDF, SQLite
**Infrastructure:** Docker Compose, Nginx

## Documentation

- [PRD](docs/prd.md) — Product requirements
- [Design Spec](docs/superpowers/specs/2026-04-05-tsunami-simulator-design-v2.md) — Architecture and API design
- [Wave Solver](docs/wave-solver.md) — Technical solver documentation
