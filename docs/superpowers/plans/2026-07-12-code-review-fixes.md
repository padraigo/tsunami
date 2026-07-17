# Code Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 10 verified defects from the 2026-07-12 code review (`docs/CODE-REVIEW-FINDINGS-2026-07-12.md`): a DoS-able public endpoint, a broken MCP mount path, three elevation-overlay rendering bugs, mismatched hardcoded ports, duplicated UI/logic, and misleading vendored docs.

**Architecture:** Backend is FastAPI (`backend/src/tsunami/`, tests in `backend/tests/` with pytest + httpx ASGI client, async tests run without markers — asyncio auto mode). Frontend is React 19 + MapLibre + Zustand (`frontend/src/`, vitest tests in `frontend/tests/` run via `npx vitest run`; MapLibre-dependent components have no tests, so map behavior is verified via `npm run build` + `npm run lint` + manual browser checks). The MCP server (`backend/src/tsunami/mcp/`) is mounted onto the FastAPI app.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy async / numpy / Pillow / pydantic-settings; TypeScript / React / MapLibre GL; MCP Python SDK (FastMCP).

**Commands:**
- Backend tests: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/ -v` (single file: `python -m pytest tests/test_api_bathymetry.py -v`)
- Frontend check: `cd /home/padraigo/Documents/tsunami/frontend && npx vitest run && npm run build && npm run lint`

**Conventions:** Follow existing test style in `backend/tests/test_api_simulations.py` (plain `async def test_*` using the `client` / `app` fixtures from `conftest.py`). Commit messages are conventional-commit style and end with:
`Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

## Task 1: Delete the unused JSON `/bathymetry/global-depth` endpoint (findings #7, part of #1)

The JSON endpoint returns `grid_bounds` of ±85° for data covering only ±80°, duplicates `tides.py` helpers, and has **zero call sites** (`api.bathymetry.globalDepth` in the frontend is never used). YAGNI: delete it and its client method. The PNG endpoint stays (it's what MapView uses).

**Files:**
- Modify: `backend/src/tsunami/api/bathymetry_routes.py` (delete lines 75–124: the whole `global_depth` function; prune imports)
- Modify: `frontend/src/services/api.ts:67-70` (delete the `bathymetry.globalDepth` method)

- [ ] **Step 1: Confirm zero call sites (guard against stale review data)**

Run: `grep -rn "globalDepth\|/bathymetry/global-depth\b" /home/padraigo/Documents/tsunami/frontend/src /home/padraigo/Documents/tsunami/backend/src --include='*.ts' --include='*.tsx' --include='*.py' | grep -v "global-depth.png"`

Expected: only the definition in `frontend/src/services/api.ts` and the route in `bathymetry_routes.py`. If anything else shows up, STOP and reassess — the endpoint is in use and needs the bounds fix (`lat_min=-80.0, lat_max=80.0`) instead of deletion.

- [ ] **Step 2: Delete the endpoint**

In `backend/src/tsunami/api/bathymetry_routes.py`, delete the entire `global_depth` function (the `@router.get("/bathymetry/global-depth")` route, lines 75–124). Then fix the imports at the top — `base64`, `create_grid`, and `JSONResponse` were only used by the deleted function:

```python
"""Bathymetry data endpoints."""

import asyncio
import io

import numpy as np
from fastapi import APIRouter, Query
from fastapi.responses import Response

from tsunami.api.tides import _get_land_mask
from tsunami.bathymetry.service import BathymetryService
from tsunami.config import get_settings

router = APIRouter(tags=["bathymetry"])
```

- [ ] **Step 3: Delete the frontend client method**

In `frontend/src/services/api.ts`, remove the whole `bathymetry` section (the PNG is fetched by URL directly in MapView, not through `apiFetch`):

```ts
  tides: {
    compute: (payload: TideComputePayload) =>
      apiFetch<FramesResponse>('/tides/compute', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  },
  presets: {
    locations: () => apiFetch<Preset[]>('/presets/locations'),
  },
```

(i.e. the `bathymetry: { globalDepth: ... },` block between `tides` and `presets` is gone.)

- [ ] **Step 4: Verify nothing broke**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/ -v`
Expected: all tests PASS (no existing test covers the deleted route).

Run: `cd /home/padraigo/Documents/tsunami/frontend && npx vitest run && npm run build && npm run lint`
Expected: 7 tests pass (they don't cover `globalDepth`), build succeeds, lint clean.

- [ ] **Step 5: Commit**

```bash
cd /home/padraigo/Documents/tsunami
git add backend/src/tsunami/api/bathymetry_routes.py frontend/src/services/api.ts
git commit -m "refactor: remove unused JSON global-depth endpoint with wrong grid_bounds

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 2: Validate `resolution_km` and fix the land-mask cache key (finding #1)

The PNG endpoint accepts any float for `resolution_km`; tiny values build a multi-billion-cell global grid (DoS), and `int(resolution_km)` in the cache filename makes fractional resolutions collide.

**Files:**
- Create: `backend/tests/test_api_bathymetry.py`
- Modify: `backend/src/tsunami/api/bathymetry_routes.py` (the `resolution_km` Query param)
- Modify: `backend/src/tsunami/api/tides.py:29` (cache filename)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_api_bathymetry.py`:

```python
"""Tests for bathymetry endpoints."""

from pathlib import Path

import pytest

from tsunami.api import tides as tides_module


@pytest.fixture(autouse=True)
def clear_land_mask_cache():
    """The in-memory land-mask cache is module-level; isolate tests."""
    tides_module._land_mask_cache.clear()
    yield
    tides_module._land_mask_cache.clear()


async def test_png_rejects_zero_resolution(client):
    resp = await client.get("/api/bathymetry/global-depth.png?resolution_km=0")
    assert resp.status_code == 422


async def test_png_rejects_negative_resolution(client):
    resp = await client.get("/api/bathymetry/global-depth.png?resolution_km=-5")
    assert resp.status_code == 422


async def test_png_rejects_dos_resolution(client):
    resp = await client.get("/api/bathymetry/global-depth.png?resolution_km=0.01")
    assert resp.status_code == 422


async def test_png_accepts_valid_resolution(client):
    resp = await client.get("/api/bathymetry/global-depth.png?resolution_km=500")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


async def test_land_mask_cache_filename_preserves_fraction(app):
    from tsunami.api.tides import _get_land_mask
    from tsunami.config import get_settings

    _get_land_mask(500.5)
    cache_dir = Path(get_settings().bathymetry_cache_dir)
    assert (cache_dir / "land_mask_500.5km.npz").exists()
    assert not (cache_dir / "land_mask_500km.npz").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/test_api_bathymetry.py -v`
Expected: the three reject tests FAIL (endpoint returns 200/500, not 422) and the cache-filename test FAILS (file is `land_mask_500km.npz`). `test_png_accepts_valid_resolution` may already pass.

- [ ] **Step 3: Add validation bounds and fix the cache key**

In `backend/src/tsunami/api/bathymetry_routes.py`, change the PNG endpoint signature:

```python
@router.get("/bathymetry/global-depth.png")
async def global_depth_png(
    resolution_km: float = Query(default=100.0, ge=10.0, le=1000.0),
):
```

(≥10 km keeps the global −80..80 × −180..180 grid under ~8M cells; ≤1000 km keeps at least a few rows.)

In `backend/src/tsunami/api/tides.py` line 29, preserve the fractional part in the disk cache key:

```python
    cache_file = cache_dir / f"land_mask_{resolution_km:g}km.npz"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/test_api_bathymetry.py tests/ -v`
Expected: all PASS (run the full suite too — the tides compute endpoint shares `_get_land_mask`).

- [ ] **Step 5: Commit**

```bash
cd /home/padraigo/Documents/tsunami
git add backend/tests/test_api_bathymetry.py backend/src/tsunami/api/bathymetry_routes.py backend/src/tsunami/api/tides.py
git commit -m "fix: bound resolution_km on global-depth.png and fix land-mask cache key collisions

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 3: Serve the MCP endpoint at `/mcp`, not `/mcp/mcp` (finding #2)

`mcp.streamable_http_app()` already serves its handler at the FastMCP setting `streamable_http_path` (default `"/mcp"`); mounting that sub-app at `"/mcp"` doubles the path. Use the MCP SDK's documented pattern: mount the sub-app at root so the endpoint lands at exactly `/mcp`. `mount_mcp` is called last in `create_app`, so the root mount doesn't shadow API routes.

**Files:**
- Create: `backend/tests/test_mcp_mount.py`
- Modify: `backend/src/tsunami/mcp/mount.py:19-21`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_mcp_mount.py`:

```python
"""Tests for the MCP server mount."""

from starlette.routing import Mount


async def test_mcp_reachable_at_slash_mcp(app):
    """The advertised endpoint is /mcp — the sub-app must resolve that path itself."""
    mounts = [r for r in app.routes if isinstance(r, Mount)]
    assert len(mounts) == 1
    mount = mounts[0]
    # Sub-app mounted at root; its internal streamable_http_path provides /mcp.
    assert mount.path == ""
    sub_paths = [r.path for r in mount.app.routes]
    assert "/mcp" in sub_paths


async def test_api_routes_not_shadowed_by_mcp_mount(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/test_mcp_mount.py -v`
Expected: `test_mcp_reachable_at_slash_mcp` FAILS (`mount.path == "/mcp"`, so the real endpoint is `/mcp/mcp`).

- [ ] **Step 3: Change the mount point**

In `backend/src/tsunami/mcp/mount.py`, change the mount and docstring:

```python
def mount_mcp(app: FastAPI) -> None:
    """Mount the MCP Streamable HTTP endpoint at /mcp.

    The sub-app serves the handler at its internal streamable_http_path
    (default "/mcp"), so it must be mounted at root — mounting it at "/mcp"
    would double the path to /mcp/mcp. mount_mcp is called after all API
    routers are registered, so the root mount only receives unmatched paths.

    The MCP session manager requires its own lifespan (task group) to run.
    We integrate it into the FastAPI app's lifespan.
    """
    # Force session manager creation
    mcp_app = mcp.streamable_http_app()
    # Mount at root: the sub-app itself routes /mcp (streamable_http_path)
    app.mount("/", mcp_app)
```

(The `combined_lifespan` wrapper below stays unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/test_mcp_mount.py tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Manual verification (live server)**

Run: `cd /home/padraigo/Documents/tsunami/backend && (python -m uvicorn tsunami.app:create_app --factory --port 8765 &) && sleep 3 && curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8765/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}'; kill %1`

Expected: a non-404 status (200 or 406, depending on session negotiation). Before the fix this returned 404.

- [ ] **Step 6: Commit**

```bash
cd /home/padraigo/Documents/tsunami
git add backend/tests/test_mcp_mount.py backend/src/tsunami/mcp/mount.py
git commit -m "fix(mcp): serve streamable HTTP endpoint at /mcp instead of /mcp/mcp

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 4: Make out-of-range polar rows transparent in the elevation PNG (finding #3)

Warp destination spans ±85° but source data covers ±80°; skipped rows stay 0.0 and `_depth_to_rgba` colors 0 as opaque green land → fake green bands over the polar oceans.

**Files:**
- Modify: `backend/src/tsunami/api/bathymetry_routes.py` (the warp loop + rgba step in `global_depth_png`)
- Test: `backend/tests/test_api_bathymetry.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api_bathymetry.py`:

```python
import io

import numpy as np


async def test_png_polar_bands_transparent(client):
    """Rows outside the ±80° data range must be transparent, not green land."""
    from PIL import Image

    resp = await client.get("/api/bathymetry/global-depth.png?resolution_km=500")
    assert resp.status_code == 200
    arr = np.asarray(Image.open(io.BytesIO(resp.content)))

    assert (arr[0, :, 3] == 0).all()      # top row (85N) transparent
    assert (arr[-1, :, 3] == 0).all()     # bottom row (85S) transparent
    assert (arr[arr.shape[0] // 2, :, 3] == 255).all()  # equator opaque
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/test_api_bathymetry.py::test_png_polar_bands_transparent -v`
Expected: FAIL — top/bottom rows have alpha 255 (opaque green).

- [ ] **Step 3: Track valid rows and zero their alpha**

In `global_depth_png`, replace the warp loop and rgba conversion:

```python
    warped = np.zeros((dst_rows, depth_ds.shape[1]), dtype=np.float32)
    valid_rows = np.zeros(dst_rows, dtype=bool)
    for row in range(dst_rows):
        frac = row / (dst_rows - 1)
        merc_val = merc_max - frac * (merc_max - merc_min)
        lat_deg = np.degrees(2 * np.arctan(np.exp(merc_val)) - np.pi / 2)
        if lat_deg > src_lat_max or lat_deg < src_lat_min:
            continue
        src_row_f = ((src_lat_max - lat_deg) / (src_lat_max - src_lat_min)) * (src_rows - 1)
        src_row = int(round(max(0, min(src_rows - 1, src_row_f))))
        warped[row, :] = depth_ds[src_row, :]
        valid_rows[row] = True

    rgba = _depth_to_rgba(warped)
    rgba[~valid_rows, :, 3] = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/test_api_bathymetry.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/padraigo/Documents/tsunami
git add backend/src/tsunami/api/bathymetry_routes.py backend/tests/test_api_bathymetry.py
git commit -m "fix: make polar rows outside data range transparent in elevation PNG

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 5: Fix PNG/basemap horizontal misalignment (finding #5)

The PNG endpoint adds one wrap column per side (~363.6° of data) but the frontend pins the image at exactly [-180, 180], squeezing the image and shifting coastlines. The wrap columns exist to hide a dateline seam in the *client-rendered tidal frames*; for a server-rendered full-world PNG they only cause misalignment. Remove them.

**Files:**
- Modify: `backend/src/tsunami/api/bathymetry_routes.py:148-149` (delete wrap-column line)
- Modify: `frontend/src/components/MapView/MapView.tsx:433` (comment only)
- Test: `backend/tests/test_api_bathymetry.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api_bathymetry.py`:

```python
async def test_png_width_has_no_wrap_columns(client):
    """Image must span exactly -180..180 — the frontend pins corners there."""
    from PIL import Image

    from tsunami.api.tides import _get_land_mask

    resp = await client.get("/api/bathymetry/global-depth.png?resolution_km=500")
    img = Image.open(io.BytesIO(resp.content))

    depth, _ = _get_land_mask(500.0)
    ny, nx = depth.shape
    sx = max(1, nx // 160)
    expected_width = len(range(0, nx, sx))
    assert img.width == expected_width
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/test_api_bathymetry.py::test_png_width_has_no_wrap_columns -v`
Expected: FAIL — width is `expected_width + 2`.

- [ ] **Step 3: Remove the wrap columns**

In `global_depth_png`, delete these two lines:

```python
    # Wrap longitudinally so the image spans past the dateline
    depth_ds = np.column_stack([depth_ds[:, -1:], depth_ds, depth_ds[:, :1]])
```

- [ ] **Step 4: Update the frontend comment**

In `frontend/src/components/MapView/MapView.tsx` (elevation overlay effect), the comment above `pngUrl` should now read:

```ts
    // Use server-rendered PNG. Span: lat -85..85 (Mercator limit), lon exactly
    // -180..180 (the PNG has no wrap columns — corners must match this span)
```

- [ ] **Step 5: Run tests and build**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/test_api_bathymetry.py -v`
Expected: all PASS.

Run: `cd /home/padraigo/Documents/tsunami/frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
cd /home/padraigo/Documents/tsunami
git add backend/src/tsunami/api/bathymetry_routes.py backend/tests/test_api_bathymetry.py frontend/src/components/MapView/MapView.tsx
git commit -m "fix: remove wrap columns from elevation PNG to align overlay with basemap

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 6: Fix the leaked `once('load')` listener in the elevation overlay (finding #4, plus dim-skip)

`'load'` fires once per map lifetime, so the deferred `addLayer` can fire after the user has toggled back to standard mode (orphaned overlay), and on later toggles never fires at all. Also move the OSM dim into `addLayer` so dimming can't be skipped when the layer isn't ready yet.

**Files:**
- Modify: `frontend/src/components/MapView/MapView.tsx:418-468` (elevation overlay effect)

- [ ] **Step 1: Rewrite the effect**

Replace the body of the elevation-overlay `useEffect` (keeping the `[mapMode]` dependency) with:

```ts
  // Elevation/depth overlay — uses a server-rendered PNG directly
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    if (mapMode !== 'elevation') {
      if (map.getLayer('depth-layer')) map.removeLayer('depth-layer')
      if (map.getSource('depth-frame')) map.removeSource('depth-frame')
      if (map.getLayer('osm')) map.setPaintProperty('osm', 'raster-opacity', 1)
      return
    }

    // Use server-rendered PNG. Span: lat -85..85 (Mercator limit), lon exactly
    // -180..180 (the PNG has no wrap columns — corners must match this span)
    const pngUrl = '/api/bathymetry/global-depth.png?resolution_km=100'
    const coordinates: [[number, number], [number, number], [number, number], [number, number]] = [
      [-180, 85],
      [180, 85],
      [180, -85],
      [-180, -85],
    ]

    const addLayer = () => {
      // Dim OSM tiles so the elevation map dominates
      if (map.getLayer('osm')) map.setPaintProperty('osm', 'raster-opacity', 0.15)
      if (map.getSource('depth-frame')) {
        (map.getSource('depth-frame') as any).updateImage({ url: pngUrl, coordinates })
      } else {
        map.addSource('depth-frame', { type: 'image', url: pngUrl, coordinates })
        const beforeLayer = map.getLayer('wave-frame-layer') ? 'wave-frame-layer'
          : map.getLayer('impact-circles') ? 'impact-circles'
          : undefined
        map.addLayer({
          id: 'depth-layer',
          type: 'raster',
          source: 'depth-frame',
          paint: {
            'raster-opacity': 0.95,
          },
        }, beforeLayer)
      }
    }

    // 'idle' (unlike 'load') fires again after every style settle, and the
    // listener is removed on cleanup so a stale callback can't re-add the
    // overlay after toggling back to standard mode.
    if (map.isStyleLoaded()) addLayer()
    else map.once('idle', addLayer)

    return () => {
      map.off('idle', addLayer)
      if (map.getLayer('depth-layer')) map.removeLayer('depth-layer')
      if (map.getSource('depth-frame')) map.removeSource('depth-frame')
    }
  }, [mapMode])
```

The changes vs. the current code: `once('load')` → `once('idle')`, `map.off('idle', addLayer)` added to cleanup, and the OSM-dim call moved from the effect body into `addLayer`.

- [ ] **Step 2: Test, build and lint**

Run: `cd /home/padraigo/Documents/tsunami/frontend && npx vitest run && npm run build && npm run lint`
Expected: 7 tests pass, build succeeds, lint clean. (MapLibre map behavior itself has no unit-test coverage — hence the manual step below.)

- [ ] **Step 3: Manual verification**

With the backend and `npm run dev` running: open the app, immediately click "Standard Map"→"Elevation View"→back before tiles finish loading. Expected: no dimmed/elevation overlay lingers in standard mode. Then toggle elevation on again after the map is idle — the overlay must appear.

- [ ] **Step 4: Commit**

```bash
cd /home/padraigo/Documents/tsunami
git add frontend/src/components/MapView/MapView.tsx
git commit -m "fix(frontend): remove leaked load listener in elevation overlay, dim OSM inside addLayer

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 7: Deduplicate ColorLegend and fix its depth labels (finding #8 + legend accuracy)

MapView renders `<ColorLegend />` unconditionally and App.tsx renders a second one at the same absolute position when `coarseResult` is set. Keep the MapView one (it's mode-aware). Also fix the DEPTH_STOPS swatches/labels to match `_depth_to_rgba`'s actual ramp, and drop the dead `'label' in s` conditional.

**Files:**
- Modify: `frontend/src/App.tsx` (remove duplicate legend + unused import + wrapper div)
- Modify: `frontend/src/components/MapView/ColorLegend.tsx` (DEPTH_STOPS values, label render)

- [ ] **Step 1: Remove the App.tsx duplicate**

In `frontend/src/App.tsx`: delete the `import ColorLegend from './components/MapView/ColorLegend'` line, and simplify the `map` prop (the wrapper div existed only to position the legend; MapView has its own `relative` container):

```tsx
        map={<MapView />}
```

`coarseResult` stays destructured — it still gates `bottom={coarseResult ? <BottomPanel /> : undefined}`.

- [ ] **Step 2: Fix ColorLegend stops and dead conditional**

The actual ramp in `_depth_to_rgba` (`bathymetry_routes.py`): land low t=0 → rgb(80,160,60) `#50a03c`; land 200 m → rgb(180,120,40) `#b47828`; land 2000 m → rgb(230,80,60) `#e6503c`; land 6000+ m → rgb(255,255,255) `#ffffff`; ocean 0 m → rgb(30,180,255) `#1eb4ff`; ocean 8000+ m → rgb(0,40,155) `#00289b`.

Replace `DEPTH_STOPS` and the label span in `frontend/src/components/MapView/ColorLegend.tsx`:

```tsx
const DEPTH_STOPS = [
  { color: '#ffffff', label: '6000+ m elev' },
  { color: '#e6503c', label: '2000 m elev' },
  { color: '#b47828', label: '200 m elev' },
  { color: '#50a03c', label: 'Sea level' },
  { color: '#1eb4ff', label: 'Shallow ocean' },
  { color: '#00289b', label: '8000+ m depth' },
]
```

and in the JSX:

```tsx
          <span className="text-slate-400">{s.label}</span>
```

- [ ] **Step 3: Test, build and lint**

Run: `cd /home/padraigo/Documents/tsunami/frontend && npx vitest run && npm run build && npm run lint`
Expected: 7 tests pass, build succeeds, lint clean (build would flag the now-unused ColorLegend import if Step 1 missed it).

- [ ] **Step 4: Manual verification**

Run a simulation in the dev app (or set `coarseResult` via an existing sim). Expected: exactly one legend at bottom-right; in Elevation View its swatches match the rendered map colors.

- [ ] **Step 5: Commit**

```bash
cd /home/padraigo/Documents/tsunami
git add frontend/src/App.tsx frontend/src/components/MapView/ColorLegend.tsx
git commit -m "fix(frontend): render single ColorLegend and match depth legend to actual ramp

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 8: Replace hardcoded MCP ports with settings (finding #6)

`tsunami_export` hardcodes `localhost:8001` while `tsunami_run_coarse`/`tsunami_compute_tides` hardcode `localhost:8000`. Split into two settings: `internal_api_url` (in-process loopback, always the port the server itself listens on) and `public_api_url` (what users open in a browser; differs under docker's 8001→8000 mapping).

**Files:**
- Modify: `backend/src/tsunami/config.py` (two new settings)
- Modify: `backend/src/tsunami/mcp/server.py:191-197, 425-431, 464-477`
- Modify: `docker-compose.yml` (backend env)
- Test: `backend/tests/test_config.py` (append), Create: `backend/tests/test_mcp_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_config.py` (match its existing style for settings construction — it uses `Settings()` with env manipulation; follow whatever pattern is there):

```python
def test_public_api_url_defaults_to_internal(monkeypatch, tmp_path):
    monkeypatch.setenv("TSUNAMI_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TSUNAMI_PUBLIC_API_URL", raising=False)
    monkeypatch.delenv("TSUNAMI_INTERNAL_API_URL", raising=False)
    from tsunami.config import Settings
    s = Settings()
    assert s.internal_api_url == "http://localhost:8000"
    assert s.public_api_url == s.internal_api_url


def test_public_api_url_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TSUNAMI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TSUNAMI_PUBLIC_API_URL", "http://localhost:8001")
    from tsunami.config import Settings
    s = Settings()
    assert s.public_api_url == "http://localhost:8001"
    assert s.internal_api_url == "http://localhost:8000"
```

Create `backend/tests/test_mcp_tools.py`:

```python
"""Tests for MCP tool functions (called directly, not over the wire)."""

import json


async def test_export_url_uses_public_api_url(app):
    from tsunami.config import get_settings
    from tsunami.mcp.server import tsunami_export

    result = json.loads(await tsunami_export("some-uid"))
    assert result["export_url"].startswith(get_settings().public_api_url)
    assert "some-uid" in result["export_url"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/test_config.py tests/test_mcp_tools.py -v`
Expected: FAIL — `Settings` has no `internal_api_url`/`public_api_url` attributes; export URL starts with `http://localhost:8001` while settings (once added) default to 8000.

- [ ] **Step 3: Add the settings**

In `backend/src/tsunami/config.py`, add to the `Settings` class fields:

```python
    internal_api_url: str = "http://localhost:8000"
    public_api_url: str = ""
```

and at the end of `model_post_init`:

```python
        if not self.public_api_url:
            self.public_api_url = self.internal_api_url
```

- [ ] **Step 4: Use them in server.py**

In `backend/src/tsunami/mcp/server.py`:

`tsunami_run_coarse` — replace:

```python
    settings = get_settings()
    backend_url = f"http://localhost:8000"
```

with:

```python
    backend_url = get_settings().internal_api_url
```

`tsunami_compute_tides` — replace the `client.post("http://localhost:8000/api/tides/compute", ...)` call with:

```python
        resp = await client.post(f"{get_settings().internal_api_url}/api/tides/compute", json={
```

`tsunami_export` — replace the return with:

```python
    return json.dumps({
        "export_url": f"{get_settings().public_api_url}/api/simulations/{uid}/export?format={format}",
        "message": f"Download results at the URL above ({format} format).",
    })
```

- [ ] **Step 5: Set the docker override**

In `docker-compose.yml`, backend service `environment` block, add:

```yaml
      TSUNAMI_PUBLIC_API_URL: http://localhost:8001
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/test_config.py tests/test_mcp_tools.py tests/ -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/padraigo/Documents/tsunami
git add backend/src/tsunami/config.py backend/src/tsunami/mcp/server.py backend/tests/test_config.py backend/tests/test_mcp_tools.py docker-compose.yml
git commit -m "fix(mcp): replace hardcoded ports with internal/public API URL settings

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 9: MCP tools validate through shared schemas; dedupe presets; delete dead code (finding #9)

`tsunami_create_simulation` and `tsunami_create_focus_zone` bypass the REST layer's pydantic validation; presets are duplicated byte-for-byte; `_get_db`, a dead `limit(1)` query, and a load-everything count are noise.

**Files:**
- Modify: `backend/src/tsunami/mcp/server.py`
- Test: `backend/tests/test_mcp_tools.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_mcp_tools.py`:

```python
async def test_create_simulation_rejects_out_of_range_magnitude(app):
    from tsunami.mcp.server import tsunami_create_simulation

    result = json.loads(await tsunami_create_simulation(
        name="bad", earthquake_lat=0.0, earthquake_lon=0.0,
        earthquake_magnitude=12.0,
    ))
    assert "error" in result


async def test_create_simulation_valid_params(app):
    from tsunami.mcp.server import tsunami_create_simulation

    result = json.loads(await tsunami_create_simulation(
        name="Tohoku test", earthquake_lat=38.3, earthquake_lon=142.4,
        earthquake_magnitude=9.1,
    ))
    assert "uid" in result


async def test_create_focus_zone_rejects_inverted_bounds(app):
    from tsunami.mcp.server import tsunami_create_focus_zone, tsunami_create_simulation

    sim = json.loads(await tsunami_create_simulation(
        name="parent", earthquake_lat=0.0, earthquake_lon=0.0,
        earthquake_magnitude=8.0,
    ))
    result = json.loads(await tsunami_create_focus_zone(
        simulation_uid=sim["uid"], name="bad zone",
        lat_min=40.0, lat_max=30.0, lon_min=10.0, lon_max=20.0,
    ))
    assert "error" in result


async def test_presets_come_from_single_source(app):
    from tsunami.api.presets import PRESET_LOCATIONS
    from tsunami.mcp.server import tsunami_list_presets

    assert json.loads(await tsunami_list_presets()) == PRESET_LOCATIONS


async def test_health_reports_count(app):
    from tsunami.mcp.server import tsunami_health

    result = json.loads(await tsunami_health())
    assert result["status"] == "ok"
    assert isinstance(result["simulation_count"], int)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/test_mcp_tools.py -v`
Expected: `rejects_out_of_range_magnitude` and `rejects_inverted_bounds` FAIL (rows get created; no error key). The presets/health/valid tests may already pass.

- [ ] **Step 3: Implement validation and dedup**

In `backend/src/tsunami/mcp/server.py`:

Top-of-file imports — add:

```python
from pydantic import ValidationError

from tsunami.api.presets import PRESET_LOCATIONS
from tsunami.schemas import FocusZoneCreate, SimulationCreate
```

and add `func` to the sqlalchemy import: `from sqlalchemy import func, select`.

Delete the dead `_get_db` generator (lines 30–33).

`tsunami_health` — replace the body's DB block:

```python
    try:
        session = await _get_session()
        async with session:
            count = (
                await session.execute(select(func.count()).select_from(Simulation))
            ).scalar_one()
        return json.dumps({"status": "ok", "simulation_count": count})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
```

`tsunami_create_simulation` — validate before touching the DB (keep the docstring; replace the body):

```python
    from datetime import datetime as dt

    try:
        payload = SimulationCreate(
            name=name,
            earthquake_lat=earthquake_lat,
            earthquake_lon=earthquake_lon,
            earthquake_magnitude=earthquake_magnitude,
            earthquake_direction=earthquake_direction,
            earthquake_depth_km=earthquake_depth_km,
            grid_resolution_km=grid_resolution_km,
            duration_hours=duration_hours,
            earthquake_datetime=dt.fromisoformat(earthquake_datetime) if earthquake_datetime else None,
        )
    except (ValidationError, ValueError) as e:
        return json.dumps({"error": f"Invalid parameters: {e}"})

    session = await _get_session()
    async with session:
        sim = Simulation(**payload.model_dump())
        session.add(sim)
        await session.commit()
        await session.refresh(sim)
        return json.dumps({
            "uid": sim.uid, "name": sim.name, "status": sim.status.value,
            "message": f"Simulation created. Run it with tsunami_run_coarse(uid='{sim.uid}')",
        }, indent=2)
```

`tsunami_create_focus_zone` — validate with the shared schema (keep the docstring; replace the body):

```python
    try:
        payload = FocusZoneCreate(
            name=name,
            lat_min=lat_min, lat_max=lat_max,
            lon_min=lon_min, lon_max=lon_max,
            source="user",
            grid_resolution_m=grid_resolution_m,
        )
    except ValidationError as e:
        return json.dumps({"error": f"Invalid parameters: {e}"})

    session = await _get_session()
    async with session:
        result = await session.execute(select(Simulation).where(Simulation.uid == simulation_uid))
        sim = result.scalar_one_or_none()
        if not sim:
            return json.dumps({"error": f"Simulation {simulation_uid} not found"})

        zone = FocusZone(
            simulation_id=sim.id,
            name=payload.name,
            lat_min=payload.lat_min, lat_max=payload.lat_max,
            lon_min=payload.lon_min, lon_max=payload.lon_max,
            source=ZoneSource.USER,
            grid_resolution_m=payload.grid_resolution_m,
        )
        session.add(zone)
        await session.commit()
        await session.refresh(zone)
        return json.dumps({
            "uid": zone.uid, "name": zone.name, "status": zone.status.value,
        }, indent=2)
```

`tsunami_list_presets` — replace the inline list:

```python
    return json.dumps(PRESET_LOCATIONS, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/test_mcp_tools.py tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/padraigo/Documents/tsunami
git add backend/src/tsunami/mcp/server.py backend/tests/test_mcp_tools.py
git commit -m "refactor(mcp): validate tool inputs via shared schemas, dedupe presets, drop dead code

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 10: Move `_get_land_mask` out of the tides route module (cleanup)

`bathymetry_routes.py` imports the underscore-private `_get_land_mask` (and its module-level cache) from the sibling route module `tides.py`. Move it to a neutral home in the bathymetry package.

**Files:**
- Create: `backend/src/tsunami/bathymetry/land_mask.py`
- Modify: `backend/src/tsunami/api/tides.py` (import instead of define)
- Modify: `backend/src/tsunami/api/bathymetry_routes.py` (import from new module)
- Modify: `backend/tests/test_api_bathymetry.py` (cache-clear fixture + imports point at new module)

- [ ] **Step 1: Create the new module**

Create `backend/src/tsunami/bathymetry/land_mask.py` (function body is moved verbatim from `tides.py`, including the Task-2 `:g` filename fix, renamed public):

```python
"""Cached low-resolution global land mask / depth grid."""

from pathlib import Path

import numpy as np

from tsunami.config import get_settings
from tsunami.simulation.grid import create_grid

_land_mask_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}


def get_land_mask(resolution_km: float) -> tuple[np.ndarray, np.ndarray]:
    """Get or compute a cached low-res global land mask."""
    key = f"{resolution_km}"
    if key in _land_mask_cache:
        return _land_mask_cache[key]

    cache_dir = Path(get_settings().bathymetry_cache_dir)
    cache_file = cache_dir / f"land_mask_{resolution_km:g}km.npz"

    if cache_file.exists():
        data = np.load(str(cache_file))
        depth, mask = data["depth"], data["mask"]
        _land_mask_cache[key] = (depth, mask)
        return depth, mask

    grid = create_grid(lat_min=-80, lat_max=80, lon_min=-180, lon_max=180, resolution_km=resolution_km)
    try:
        from tsunami.bathymetry.service import BathymetryService
        svc = BathymetryService(cache_dir=str(cache_dir))
        depth = svc.get_bathymetry(grid, source="gebco")
        depth = np.nan_to_num(depth, nan=0.0, posinf=0.0, neginf=0.0)
    except Exception:
        depth = np.ones(grid.depth.shape) * 4000.0

    mask = depth <= 0
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(cache_file), depth=depth.astype(np.float32), mask=mask)
    _land_mask_cache[key] = (depth, mask)
    return depth, mask
```

- [ ] **Step 2: Update the importers**

In `backend/src/tsunami/api/tides.py`: delete the `_land_mask_cache` dict and the `_get_land_mask` function (lines 19–50), delete the now-unused `from pathlib import Path` import, add `from tsunami.bathymetry.land_mask import get_land_mask`, and change the call site in `compute_tides` to `await asyncio.to_thread(get_land_mask, body.resolution_km)`.

In `backend/src/tsunami/api/bathymetry_routes.py`: replace `from tsunami.api.tides import _get_land_mask` with `from tsunami.bathymetry.land_mask import get_land_mask` and update the call site to `await asyncio.to_thread(get_land_mask, resolution_km)`.

In `backend/tests/test_api_bathymetry.py`: change the fixture and test imports:

```python
from tsunami.bathymetry import land_mask as land_mask_module


@pytest.fixture(autouse=True)
def clear_land_mask_cache():
    """The in-memory land-mask cache is module-level; isolate tests."""
    land_mask_module._land_mask_cache.clear()
    yield
    land_mask_module._land_mask_cache.clear()
```

and in the two tests that import it, use `from tsunami.bathymetry.land_mask import get_land_mask` / `get_land_mask(...)`.

- [ ] **Step 3: Verify no stragglers**

Run: `grep -rn "_get_land_mask" /home/padraigo/Documents/tsunami/backend/src /home/padraigo/Documents/tsunami/backend/tests`
Expected: no matches.

- [ ] **Step 4: Run the full backend suite**

Run: `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/padraigo/Documents/tsunami
git add backend/src/tsunami/bathymetry/land_mask.py backend/src/tsunami/api/tides.py backend/src/tsunami/api/bathymetry_routes.py backend/tests/test_api_bathymetry.py
git commit -m "refactor: move land-mask cache to tsunami.bathymetry.land_mask

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 11: Relocate the vendored ECC files and write a real CLAUDE.md (finding #10)

> **⚠️ REQUIRES EXPLICIT USER CONFIRMATION BEFORE EXECUTING.** This task moves ~800 untracked files out of the repo. Several look like the user's own working documents for the "Everything Claude Code" project (e.g. `WORKING-CONTEXT.md`, `docs/PR-QUEUE-TRIAGE-2026-03-13.md`, `REPO-ASSESSMENT.md`) — they must be **moved, never deleted**, and the user must confirm the destination. Present the file list and destination to the user and wait for a yes.

**Files:**
- Move: all untracked ECC-origin files/dirs (list below) → `~/Documents/ecc-recovered-2026-07-12/`
- Create: `CLAUDE.md` (new, tsunami-specific)
- Keep in place: `docs/CODE-REVIEW-FINDINGS-2026-07-12.md`, `docs/superpowers/`, `backend/data/` (runtime data), and — pending inspection — `.gitignore`, `.claude/settings.json`, root `data/`

- [ ] **Step 1: Inspect the ambiguous items before moving anything**

Run: `cat /home/padraigo/Documents/tsunami/.gitignore; echo ===; cat /home/padraigo/Documents/tsunami/.claude/settings.json; echo ===; ls /home/padraigo/Documents/tsunami/data/`

Decide per item: keep `.gitignore` if its rules fit a Python/Node repo (edit out ECC-specific entries); keep `.claude/settings.json` if it contains this user's local permission settings (likely — do not move it without asking); root `data/` — if it contains ECC sample data, move it; if tsunami runtime data, keep.

- [ ] **Step 2: Present the move list to the user and get confirmation**

The ECC-origin set (everything untracked at repo root except the keep-list):

```
AGENTS.md CHANGELOG.md CODE_OF_CONDUCT.md COMMANDS-QUICK-REF.md CONTRIBUTING.md
EVALUATION.md LICENSE README.zh-CN.md REPO-ASSESSMENT.md RULES.md SECURITY.md
SOUL.md SPONSORING.md SPONSORS.md TROUBLESHOOTING.md VERSION WORKING-CONTEXT.md
CLAUDE.md agent.yaml commitlint.config.js eslint.config.js package.json
package-lock.json yarn.lock install.sh install.ps1
the-longform-guide.md the-security-guide.md the-shortform-guide.md
agents/ assets/ commands/ contexts/ ecc2/ examples/ hooks/ manifests/
mcp-configs/ plugins/ research/ rules/ schemas/ scripts/ skills/ tests/
docs/ANTIGRAVITY-GUIDE.md docs/ARCHITECTURE-IMPROVEMENTS.md docs/COMMAND-AGENT-MAP.md
docs/ECC-2.0-REFERENCE-ARCHITECTURE.md docs/ECC-2.0-SESSION-ADAPTER-DISCOVERY.md
docs/HERMES-OPENCLAW-MIGRATION.md docs/HERMES-SETUP.md docs/MANUAL-ADAPTATION-GUIDE.md
docs/MEGA-PLAN-REPO-PROMPTS-2026-03-12.md docs/PHASE1-ISSUE-BUNDLE-2026-03-12.md
docs/PR-399-REVIEW-2026-03-12.md docs/PR-QUEUE-TRIAGE-2026-03-13.md
docs/SELECTIVE-INSTALL-ARCHITECTURE.md docs/SELECTIVE-INSTALL-DESIGN.md
docs/SESSION-ADAPTER-CONTRACT.md docs/SKILL-DEVELOPMENT-GUIDE.md
docs/SKILL-PLACEMENT-POLICY.md docs/TROUBLESHOOTING.md docs/business/
docs/continuous-learning-v2-spec.md docs/examples/ docs/ja-JP/ docs/ko-KR/
docs/pt-BR/ docs/releases/ docs/token-optimization.md docs/tr/ docs/zh-CN/ docs/zh-TW/
```

Note for the user: `backend/src/tsunami/mcp/` and `backend/data/` are **tsunami** files (new MCP feature + runtime data) and stay. `mv` of `LICENSE` leaves the repo unlicensed — flag that they may want to add a license for the tsunami project itself.

- [ ] **Step 3 (after confirmation): Move the files**

```bash
mkdir -p ~/Documents/ecc-recovered-2026-07-12/docs
cd /home/padraigo/Documents/tsunami
mv AGENTS.md CHANGELOG.md CODE_OF_CONDUCT.md COMMANDS-QUICK-REF.md CONTRIBUTING.md \
   EVALUATION.md LICENSE README.zh-CN.md REPO-ASSESSMENT.md RULES.md SECURITY.md \
   SOUL.md SPONSORING.md SPONSORS.md TROUBLESHOOTING.md VERSION WORKING-CONTEXT.md \
   CLAUDE.md agent.yaml commitlint.config.js eslint.config.js package.json \
   package-lock.json yarn.lock install.sh install.ps1 \
   the-longform-guide.md the-security-guide.md the-shortform-guide.md \
   agents assets commands contexts ecc2 examples hooks manifests \
   mcp-configs plugins research rules schemas scripts tests skills \
   ~/Documents/ecc-recovered-2026-07-12/
mv docs/ANTIGRAVITY-GUIDE.md docs/ARCHITECTURE-IMPROVEMENTS.md docs/COMMAND-AGENT-MAP.md \
   docs/ECC-2.0-REFERENCE-ARCHITECTURE.md docs/ECC-2.0-SESSION-ADAPTER-DISCOVERY.md \
   docs/HERMES-OPENCLAW-MIGRATION.md docs/HERMES-SETUP.md docs/MANUAL-ADAPTATION-GUIDE.md \
   docs/MEGA-PLAN-REPO-PROMPTS-2026-03-12.md docs/PHASE1-ISSUE-BUNDLE-2026-03-12.md \
   docs/PR-399-REVIEW-2026-03-12.md docs/PR-QUEUE-TRIAGE-2026-03-13.md \
   docs/SELECTIVE-INSTALL-ARCHITECTURE.md docs/SELECTIVE-INSTALL-DESIGN.md \
   docs/SESSION-ADAPTER-CONTRACT.md docs/SKILL-DEVELOPMENT-GUIDE.md \
   docs/SKILL-PLACEMENT-POLICY.md docs/TROUBLESHOOTING.md docs/business \
   docs/continuous-learning-v2-spec.md docs/examples docs/ja-JP docs/ko-KR \
   docs/pt-BR docs/releases docs/token-optimization.md docs/tr docs/zh-CN docs/zh-TW \
   ~/Documents/ecc-recovered-2026-07-12/docs/
```

Then verify what remains: `git status --short` should show only tsunami-related modified/untracked files (`docs/CODE-REVIEW-FINDINGS-2026-07-12.md`, `docs/superpowers/`, `backend/data/`, `backend/src/tsunami/mcp/`, plus whatever Step 1 decided to keep).

- [ ] **Step 4: Write the real CLAUDE.md**

Create `/home/padraigo/Documents/tsunami/CLAUDE.md`:

```markdown
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

- Run tests: `python -m pytest tests/ -v`
- Dev server: `python -m uvicorn tsunami.app:create_app --factory --reload`
- Settings via `TSUNAMI_*` env vars (see `src/tsunami/config.py`)

### Frontend (from `frontend/`)

- Dev server: `npm run dev`
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
- Map overlays (waves, tides, elevation) are image sources placed on the
  MapLibre map; the elevation overlay is a server-rendered Mercator-warped
  PNG from `/api/bathymetry/global-depth.png`.

## Conventions

- Backend tests are plain `async def` pytest functions using the `client` /
  `app` fixtures in `backend/tests/conftest.py`.
- Conventional-commit style commit messages.
```

- [ ] **Step 5: Commit**

```bash
cd /home/padraigo/Documents/tsunami
git add CLAUDE.md
git commit -m "docs: replace vendored ECC CLAUDE.md with tsunami project guidance

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(The moved ECC files were untracked, so the move itself needs no commit.)

---

## Verification (whole plan)

- [ ] `cd /home/padraigo/Documents/tsunami/backend && python -m pytest tests/ -v` — all pass
- [ ] `cd /home/padraigo/Documents/tsunami/frontend && npx vitest run && npm run build && npm run lint` — clean
- [ ] Manual sweep with `docker compose up` or dev servers: elevation toggle (no orphan overlay, no green polar bands, coastlines aligned at the dateline), single legend with correct colors, `curl -X POST http://localhost:8001/mcp ...` returns non-404, MCP `tsunami_export` URL opens.

## Deliberately not addressed

- The per-row Python warp loop in `global_depth_png` (works, minor efficiency nit; response is cached an hour).
- The same leaked-`'load'`-listener pattern in the inundation and wave-frame effects (`MapView.tsx:409`, `:523`) — pre-existing, lower impact because those effects re-run on data changes; fix opportunistically if touching those effects.
