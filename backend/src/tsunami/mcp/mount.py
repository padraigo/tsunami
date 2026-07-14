"""Mount the MCP server on the FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.routing import Mount

from tsunami.mcp.server import mcp


def mount_mcp(app: FastAPI) -> None:
    """Mount the MCP Streamable HTTP endpoint at /mcp.

    The sub-app serves the handler at its internal streamable_http_path
    (default "/mcp"), so it must be mounted at root — mounting it at "/mcp"
    would double the path to /mcp/mcp. mount_mcp is called after all API
    routers are registered, so the root mount only receives unmatched paths.

    The MCP session manager requires its own lifespan (task group) to run,
    and can only be run once per instance — reset it so every created app
    gets a fresh, runnable manager (the FastMCP object is module-level).

    Side effect of the root mount: unmatched request paths app-wide receive
    the MCP sub-app's plain-text 404 rather than FastAPI's JSON
    {"detail": "Not Found"}, and a root StaticFiles mount is foreclosed
    while the MCP app owns "/".
    """
    # No public reset API in the SDK; streamable_http_app() lazily recreates it.
    # Guarded by test_repeated_app_creation_gets_fresh_session_manager.
    mcp._session_manager = None
    mcp_app = mcp.streamable_http_app()
    session_manager = mcp.session_manager
    # Mount at root: the sub-app itself routes /mcp (streamable_http_path)
    app.mount("/", mcp_app)

    # Wrap the existing lifespan to also start the MCP session manager
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app_instance):
        async with original_lifespan(app_instance) as original_state:
            async with session_manager.run():
                yield original_state

    app.router.lifespan_context = combined_lifespan
