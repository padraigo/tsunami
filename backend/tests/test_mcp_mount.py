"""Tests for the MCP server mount."""

from starlette.routing import Mount

from tsunami.app import create_app


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


async def test_repeated_app_creation_gets_fresh_session_manager(app):
    """Module-level FastMCP must not reuse a session manager across apps.

    StreamableHTTPSessionManager.run() raises on a second call per instance;
    each create_app() must therefore get a fresh manager.
    """
    from tsunami.mcp.server import mcp

    first_manager = mcp.session_manager
    second_app = create_app()
    assert mcp.session_manager is not first_manager


async def test_unmatched_path_gets_subapp_404(client):
    """Root-mounting the MCP sub-app changes the 404 shape for unknown paths.

    Deliberate trade-off (see mount_mcp docstring): unknown paths fall through
    to the MCP sub-app's plain-text 404 instead of FastAPI's JSON 404.
    """
    resp = await client.get("/api/nonexistent")
    assert resp.status_code == 404


async def test_mcp_endpoint_functional_with_lifespan(app):
    """End-to-end: with the lifespan running, POST /mcp actually answers.

    Guards the combined_lifespan wiring — the structural mount test alone
    would stay green if the session manager were never started.
    """
    from httpx import ASGITransport, AsyncClient

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://localhost:8000",
        ) as ac:
            resp = await ac.post(
                "/mcp",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "t", "version": "0"},
                    },
                },
            )
    assert resp.status_code == 200
