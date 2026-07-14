"""Mount the MCP server on the FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.routing import Mount

from tsunami.mcp.server import mcp


def mount_mcp(app: FastAPI) -> None:
    """Mount the MCP Streamable HTTP endpoint at /mcp.

    The MCP session manager requires its own lifespan (task group) to run.
    We integrate it into the FastAPI app's lifespan and mount the ASGI handler
    directly rather than using the Starlette sub-app wrapper.
    """
    # Force session manager creation
    mcp_app = mcp.streamable_http_app()
    # Mount the full Starlette sub-app (it has its own lifespan)
    app.mount("/mcp", mcp_app)

    # Wrap the existing lifespan to also start the MCP session manager
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app_instance):
        async with original_lifespan(app_instance) as original_state:
            async with mcp.session_manager.run():
                yield original_state

    app.router.lifespan_context = combined_lifespan
