"""Tests for MCP tool functions (called directly, not over the wire)."""

import json


async def test_export_url_uses_public_api_url(app):
    from tsunami.config import get_settings
    from tsunami.mcp.server import tsunami_export

    result = json.loads(await tsunami_export("some-uid"))
    assert result["export_url"].startswith(get_settings().public_api_url)
    assert "some-uid" in result["export_url"]
