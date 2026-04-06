import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from tsunami.app import create_app


@pytest.fixture
def rng():
    """Seeded random number generator for reproducible tests."""
    return np.random.default_rng(42)


@pytest.fixture
def flat_depth():
    """Uniform ocean depth of 4000m (typical open ocean)."""
    return 4000.0


@pytest.fixture
def gravity():
    """Standard gravitational acceleration."""
    return 9.81


@pytest.fixture
async def app(tmp_path):
    """Create a test FastAPI app with a temporary database."""
    import os
    old_data_dir = os.environ.get("TSUNAMI_DATA_DIR")
    old_db_url = os.environ.get("TSUNAMI_DATABASE_URL")
    os.environ["TSUNAMI_DATA_DIR"] = str(tmp_path / "data")
    os.environ["TSUNAMI_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    from tsunami.config import get_settings
    get_settings.cache_clear()
    from tsunami.api.deps import reset_engine, _get_engine
    reset_engine()
    application = create_app()
    # Create tables (lifespan not triggered by ASGITransport)
    from tsunami.database import Base
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield application
    await engine.dispose()
    # Restore environment
    if old_data_dir is None:
        os.environ.pop("TSUNAMI_DATA_DIR", None)
    else:
        os.environ["TSUNAMI_DATA_DIR"] = old_data_dir
    if old_db_url is None:
        os.environ.pop("TSUNAMI_DATABASE_URL", None)
    else:
        os.environ["TSUNAMI_DATABASE_URL"] = old_db_url
    get_settings.cache_clear()
    reset_engine()


@pytest.fixture
async def client(app):
    """Async test client for the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
