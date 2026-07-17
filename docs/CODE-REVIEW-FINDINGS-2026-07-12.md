# Code Review Findings — 2026-07-12

High-effort multi-agent review of the working tree on `feat/simulation-engine` (bathymetry endpoints, MCP server, elevation view). 33 verified candidates collapsed into 10 distinct defects; none refuted in verification.

## Correctness

### 1. DoS via unvalidated `resolution_km` (CONFIRMED)
**Where:** `backend/src/tsunami/api/bathymetry_routes.py:77` (also `:129`)

The public `/api/bathymetry/global-depth` and `/api/bathymetry/global-depth.png` endpoints declare `resolution_km: float = Query(default=100.0)` with no bounds, unlike `TideComputeRequest`'s `Field(gt=0)`. The value flows straight into a global-extent `create_grid` / `_get_land_mask` computation.

- `?resolution_km=0.01` → global −80..80 × −180..180 grid with billions of cells → memory exhaustion, backend killed by one unauthenticated request.
- `resolution_km=0` or negative → exception inside `create_grid` → 500.
- The land-mask disk cache key uses `int(resolution_km)`, so `0.5` and `0.9` collide on `land_mask_0km.npz` and later requests can be served a wrong-resolution depth grid.

**Fix:** validated bounds (e.g. `Query(default=100.0, gt=0, ge=some_min, le=some_max)` or `ge=10, le=500`), and a cache key that preserves the fractional resolution.

### 2. MCP endpoint actually served at `/mcp/mcp` (CONFIRMED)
**Where:** `backend/src/tsunami/mcp/mount.py:21`

`mcp.streamable_http_app()` already serves the streamable HTTP handler at its internal `streamable_http_path` (default `"/mcp"`). Mounting that sub-app at `"/mcp"` puts the real endpoint at `/mcp/mcp`. Clients configured with the documented `http://localhost:8000/mcp` get a 404.

**Fix:** set `streamable_http_path="/"` on the FastMCP instance (or mount the sub-app at root), keeping the effective endpoint at `/mcp`.

### 3. Opaque green polar bands in elevation PNG (CONFIRMED)
**Where:** `backend/src/tsunami/api/bathymetry_routes.py:171–177`

The Mercator warp destination spans ±85° but source data covers ±80°. Rows with |lat| in (80, 85] are skipped (`continue`), left at the `np.zeros` init value 0.0, and `_depth_to_rgba` colors depth==0 as opaque land green (80,160,60,255). Users see fake green horizontal strips over the Arctic/Antarctic from 80°–85°.

**Fix:** make out-of-range rows transparent (e.g. track a valid-mask, or fill with NaN and map NaN → alpha 0 in `_depth_to_rgba`).

### 4. Leaked `map.once('load')` listener orphans the elevation overlay (CONFIRMED)
**Where:** `frontend/src/components/MapView/MapView.tsx:462`

The elevation-overlay effect registers `map.once('load', addLayer)` but cleanup (lines 464–467) never calls `map.off('load', addLayer)`. MapLibre `'load'` fires once per map lifetime.

- Toggle elevation on→off before the initial style load: the stale callback later adds the dimmed overlay while in standard mode, with no cleanup path (orphaned until the user toggles elevation on/off again).
- On later toggles when `isStyleLoaded()` is transiently false, `once('load')` never fires again → overlay silently never appears.

**Fix:** remove the listener in cleanup and use an event that can re-fire (`'idle'`) or a `style.load`/retry pattern for post-initial-load cases.

### 5. PNG wrap columns squeezed into [-180, 180] (CONFIRMED)
**Where:** `backend/src/tsunami/api/bathymetry_routes.py:149` + `frontend/src/components/MapView/MapView.tsx:435–440`

The PNG endpoint adds one wrap column on each side (`np.column_stack([depth_ds[:, -1:], depth_ds, depth_ds[:, :1]])`), so the image spans 360° + 2·dlon, but the frontend pins the image corners at exactly [-180, 180] — squeezing ~363.6° into 360°. Overlay coastlines misalign with the basemap by up to one downsampled cell (~1.8° at 100 km), worst near the dateline. The tidal-frame path handles this correctly by extending `grid_bounds` to −180−dlon..180+dlon (`tides.py`).

**Fix:** either drop the wrap columns from the PNG, or have the endpoint report its true lon bounds and use them for the image corners (matching the tidal-frame approach).

### 6. Mismatched hardcoded ports in MCP tools (CONFIRMED)
**Where:** `backend/src/tsunami/mcp/server.py:475` vs `:192`/`:427`

`tsunami_export` hardcodes `http://localhost:8001/...` while `tsunami_run_coarse` and `tsunami_compute_tides` hardcode `http://localhost:8000`. Docker maps host 8001 → container 8000; bare uvicorn serves 8000 everywhere. Whatever the deployment, one of the tools emits a dead URL (bare uvicorn: export URL refused on 8001).

**Fix:** single configurable base URL (settings/env var) for both in-process API calls and externally-visible export URLs (these may legitimately differ — internal vs public base URL settings).

### 7. JSON endpoint's `grid_bounds` claims ±85° for ±80° data (CONFIRMED)
**Where:** `backend/src/tsunami/api/bathymetry_routes.py:113` (also `:75`)

`/bathymetry/global-depth` returns `grid_bounds` `lat_min=-85 / lat_max=85` but the depth array from `_get_land_mask` covers only −80..80 (the PNG endpoint pre-warps/pads for ±85; the JSON endpoint does not). Any consumer placing the grid by these bounds stretches 160° of data over 170° — rows misplaced by up to ~5°. Currently latent: `api.bathymetry.globalDepth` in `frontend/src/services/api.ts` has no call sites.

**Fix:** return the true bounds (±80) — or remove the unused endpoint/client method entirely.

### 8. Two ColorLegends render simultaneously (CONFIRMED)
**Where:** `frontend/src/components/MapView/MapView.tsx:544` + `frontend/src/App.tsx:33`

MapView now renders `<ColorLegend />` unconditionally while App.tsx still renders `{coarseResult && <ColorLegend />}` at the identical absolute position (`bottom-20 right-4`). After any simulation run, both mount stacked — doubled, garbled legend.

**Fix:** remove the App.tsx instance (MapView's is now mode-aware).

## Cleanup

### 9. MCP tools duplicate the API layer with direct DB writes (CONFIRMED)
**Where:** `backend/src/tsunami/mcp/server.py` (pattern throughout; e.g. `:192`)

Two tools (`tsunami_run_coarse`, `tsunami_compute_tides`) delegate to the REST API over HTTP; the rest re-implement list/get/create/delete with direct DB access, bypassing REST validation — e.g. `tsunami_create_simulation` inserts a `Simulation` directly without enforcing the magnitude/duration bounds its own docstring promises. Business logic exists in two places and will drift.

Related confirmed details:
- Dead code: `_get_db` generator (`server.py:30–33`) never used; `settings = get_settings()` at `:191` unused; dead `select(Simulation).limit(1)` query at `:50–53`; health check loads all simulations just to count them.
- `PRESET_LOCATIONS` duplicated byte-for-byte at `server.py:279–286`.

**Fix:** route all MCP tools through shared validated service functions (or the REST layer), import presets from the single source, delete dead code.

### 10. Repo-root CLAUDE.md/AGENTS.md + ~750 vendored ECC docs describe a different project (CONFIRMED)
**Where:** `CLAUDE.md:7`, `AGENTS.md`, `README.zh-CN.md`, `docs/{ja-JP,ko-KR,pt-BR,tr,zh-CN,zh-TW}/` (712 files, ~6.9 MB), plus `agents/`, `skills/`, `hooks/`, `commands/`, `rules/`, `scripts/`, `tests/`, `plugins/`, etc.

The untracked root docs are the "Everything Claude Code" (ECC) plugin repo's content dropped into the tsunami repo. CLAUDE.md claims the repo is a Claude Code plugin, gives `node tests/run-all.js` as the test command, and describes agents/skills/hooks architecture. CLAUDE.md is auto-loaded as authoritative instructions in every Claude Code session, so agents are systematically misled about what this repo is.

**Fix:** remove the ECC files from the working tree (they are all untracked; the tracked repo is 115 files of backend/frontend tsunami code), then write a real tsunami CLAUDE.md (FastAPI backend, React/MapLibre frontend, actual test commands).

## Smaller confirmed observations

- `bathymetry_routes.py` duplicates `tides.py` helpers verbatim (`add_wrap_cols`, dlon computation, per-row Mercator warp loop) — extract shared helpers.
- `create_grid` in `global_depth` allocates a full global grid only to compute `dlon` (`bathymetry_routes.py:80–84`, used at `:108–109`).
- `bathymetry_routes.py:11` imports the underscore-private `_get_land_mask` from the sibling route module `tides.py` — shared cache/helper belongs in a neutral module.
- `ColorLegend.tsx:31`: `'label' in s` is always true — dead conditional.
- `ColorLegend.tsx` depth labels don't match the actual ramp (`#1eb4ff` is depth 0 in `_depth_to_rgba`, not "200 m depth").
- `MapView.tsx:431`: OSM dimming (`raster-opacity` 0.15) happens synchronously in the effect body but not inside `addLayer`, so if the layer isn't ready the dim can be skipped (PLAUSIBLE).

## Review stats

- Level: high (multi-agent workflow), 30 agents, ~904k tokens
- 4 finders → 33 candidates → 24 verifiers → 33 verified, 0 refuted → 10 distinct defects
