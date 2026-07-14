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


async def test_tides_compute_rejects_dos_resolution(client):
    """POST /tides/compute shares the same land-mask sink and needs the same bounds."""
    resp = await client.post("/api/tides/compute", json={
        "start_datetime": "2026-01-01T00:00:00Z",
        "resolution_km": 0.01,
    })
    assert resp.status_code == 422


async def test_land_mask_cache_filename_preserves_fraction(app):
    from tsunami.api.tides import _get_land_mask
    from tsunami.config import get_settings

    _get_land_mask(500.5)
    cache_dir = Path(get_settings().bathymetry_cache_dir)
    assert (cache_dir / "land_mask_500.5km.npz").exists()
    assert not (cache_dir / "land_mask_500km.npz").exists()
