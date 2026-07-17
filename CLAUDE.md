# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

Web-based tsunami simulation platform: earthquake-generated tsunami modeling
(Okada fault model → shallow-water-equation solver → Boussinesq detail zones)
with real-time wave propagation visualization on a MapLibre map.

- **backend/** — FastAPI + SQLAlchemy (async, SQLite) + Celery workers.
  Physics solvers and bathymetry (GEBCO) live in `backend/src/tsunami/`.
  An MCP server for AI-assistant access is mounted at `/mcp`
  (`backend/src/tsunami/mcp/`).
- **frontend/** — React 19 + TypeScript + Vite + Tailwind + MapLibre GL +
  Zustand (`frontend/src/`).

## Commands

### Backend (from `backend/`)

- Run tests: `.venv/bin/python -m pytest tests/ -v`
- Dev server: `.venv/bin/python -m uvicorn tsunami.app:create_app --factory --reload`
- Settings via `TSUNAMI_*` env vars (see `src/tsunami/config.py`)

### Frontend (from `frontend/`)

- Dev server: `npm run dev` (port 5173, proxies `/api` to :8000)
- Tests: `npx vitest run`
- Build + typecheck: `npm run build`
- Lint: `npm run lint`

### Full stack

- `docker compose up` — backend on host port 8001, frontend on 3000

## Architecture Notes

- API routers live in `backend/src/tsunami/api/`, all mounted under `/api`.
- Long-running simulations execute via Celery (`tsunami/workers/`); progress
  is broadcast over WebSocket (`/api/ws`).
- Request/response validation uses the pydantic schemas in
  `tsunami/schemas.py` — MCP tools must validate through these same schemas,
  never insert into the DB unvalidated.
- The MCP sub-app is mounted at the ASGI root (its internal path provides
  `/mcp`) and must stay the LAST mount in `create_app()`; see the
  `mount_mcp` docstring for the 404-shape trade-off.
- Map overlays (waves, tides, elevation) are image sources placed on the
  MapLibre map; the elevation overlay is a server-rendered Mercator-warped
  PNG from `/api/bathymetry/global-depth.png` spanning exactly lon -180..180.
- The global land-mask/depth cache lives in `tsunami/bathymetry/land_mask.py`
  (in-memory + `.npz` disk tiers, keyed by `:g`-formatted resolution).

## Conventions

- Backend tests are plain `async def` pytest functions using the `client` /
  `app` fixtures in `backend/tests/conftest.py` (asyncio auto mode).
- Conventional-commit style commit messages.
- Key docs: `docs/prd.md`, `docs/wave-solver.md`,
  `docs/CODE-REVIEW-FINDINGS-2026-07-12.md`.
