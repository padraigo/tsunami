"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tsunami.config import get_settings
from tsunami.database import Base
from tsunami.api.deps import _get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Tsunami Simulator API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    from tsunami.api import simulations, focus_zones, run, export, bathymetry_routes, presets, frames, tides
    app.include_router(simulations.router, prefix="/api")
    app.include_router(focus_zones.router, prefix="/api")
    app.include_router(run.router, prefix="/api")
    app.include_router(export.router, prefix="/api")
    app.include_router(bathymetry_routes.router, prefix="/api")
    app.include_router(presets.router, prefix="/api")
    app.include_router(frames.router, prefix="/api")
    app.include_router(tides.router, prefix="/api")
    from tsunami.api import websocket as ws_module
    app.include_router(ws_module.router, prefix="/api")

    # Mount MCP server for AI assistant access
    from tsunami.mcp.mount import mount_mcp
    mount_mcp(app)

    return app
