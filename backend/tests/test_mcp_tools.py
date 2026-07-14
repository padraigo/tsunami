"""Tests for MCP tool functions (called directly, not over the wire)."""

import json


async def test_export_url_uses_public_api_url(app):
    from tsunami.config import get_settings
    from tsunami.mcp.server import tsunami_export

    result = json.loads(await tsunami_export("some-uid"))
    assert result["export_url"].startswith(get_settings().public_api_url)
    assert "some-uid" in result["export_url"]


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
