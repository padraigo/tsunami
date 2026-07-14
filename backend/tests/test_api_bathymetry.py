"""Tests for bathymetry endpoints."""

import io
from pathlib import Path

import numpy as np
import pytest

from tsunami.bathymetry import land_mask as land_mask_module


@pytest.fixture(autouse=True)
def clear_land_mask_cache():
    """The in-memory land-mask cache is module-level; isolate tests."""
    land_mask_module._land_mask_cache.clear()
    yield
    land_mask_module._land_mask_cache.clear()


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


async def test_tides_compute_rejects_dos_resolution(client):
    """POST /tides/compute shares the same land-mask sink and needs the same bounds."""
    resp = await client.post("/api/tides/compute", json={
        "start_datetime": "2026-01-01T00:00:00Z",
        "resolution_km": 0.01,
    })
    assert resp.status_code == 422


async def test_png_polar_bands_transparent(client):
    """Rows outside the ±80° data range must be transparent, not green land."""
    from PIL import Image

    resp = await client.get("/api/bathymetry/global-depth.png?resolution_km=500")
    assert resp.status_code == 200
    arr = np.asarray(Image.open(io.BytesIO(resp.content)))

    assert (arr[0, :, 3] == 0).all()      # top row (85N) transparent
    assert (arr[-1, :, 3] == 0).all()     # bottom row (85S) transparent
    assert (arr[arr.shape[0] // 2, :, 3] == 255).all()  # equator opaque


async def test_png_width_has_no_wrap_columns(client):
    """Image must span exactly -180..180 — the frontend pins corners there."""
    from PIL import Image

    from tsunami.bathymetry.land_mask import get_land_mask

    resp = await client.get("/api/bathymetry/global-depth.png?resolution_km=500")
    img = Image.open(io.BytesIO(resp.content))

    depth, _ = get_land_mask(500.0)
    ny, nx = depth.shape
    sx = max(1, nx // 160)
    expected_width = len(range(0, nx, sx))
    assert img.width == expected_width


async def test_land_mask_cache_filename_preserves_fraction(app):
    from tsunami.bathymetry.land_mask import get_land_mask
    from tsunami.config import get_settings

    get_land_mask(500.5)
    cache_dir = Path(get_settings().bathymetry_cache_dir)
    assert (cache_dir / "land_mask_500.5km.npz").exists()
    assert not (cache_dir / "land_mask_500km.npz").exists()
