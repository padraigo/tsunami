# Backend API + Workers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI backend with REST API, WebSocket real-time updates, SQLAlchemy persistence, Celery background workers, and a bathymetry data service — connecting the simulation engine (Plan 1) to a web frontend.

**Architecture:** FastAPI serves REST endpoints and WebSocket connections. Coarse SWE simulation runs in-process for interactive speed. Detail (Boussinesq) simulations run as Celery tasks via Redis. SQLite stores simulation metadata; result files (NetCDF, GeoJSON) live on the filesystem. A bathymetry service provides GEBCO data with procedural fallback.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2.0 (async SQLite), Celery, Redis, Pydantic v2, pytest, httpx (test client)

---

## File Structure

```
backend/
├── pyproject.toml                                # Updated with new dependencies
├── src/tsunami/
│   ├── __init__.py
│   ├── config.py                                 # Settings via pydantic-settings
│   ├── database.py                               # SQLAlchemy engine, session, Base
│   ├── models.py                                 # SQLAlchemy ORM models
│   ├── schemas.py                                # Pydantic request/response schemas
│   ├── app.py                                    # FastAPI app factory
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                               # Dependency injection (get_db, etc.)
│   │   ├── simulations.py                        # /api/simulations routes
│   │   ├── focus_zones.py                        # /api/simulations/{id}/focus-zones routes
│   │   ├── run.py                                # /api/simulations/{id}/run-coarse, run-detail
│   │   ├── export.py                             # /api/simulations/{id}/export
│   │   ├── bathymetry_routes.py                  # /api/bathymetry routes
│   │   ├── presets.py                            # /api/presets/locations
│   │   └── websocket.py                          # WS /api/ws/simulations/{id}
│   ├── bathymetry/
│   │   ├── __init__.py
│   │   ├── procedural.py                         # (existing)
│   │   └── service.py                            # Unified bathymetry interface
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── celery_app.py                         # Celery instance + config
│   │   └── tasks.py                              # Celery task definitions
│   └── simulation/                               # (existing, unchanged)
│       ├── __init__.py
│       ├── grid.py
│       ├── okada.py
│       ├── swe_solver.py
│       ├── boussinesq.py
│       ├── impact.py
│       └── inundation.py
└── tests/
    ├── conftest.py                               # Updated with API fixtures
    ├── test_grid.py                              # (existing)
    ├── test_okada.py                             # (existing)
    ├── test_swe_solver.py                        # (existing)
    ├── test_boussinesq.py                        # (existing)
    ├── test_impact.py                            # (existing)
    ├── test_inundation.py                        # (existing)
    ├── test_procedural_bathy.py                  # (existing)
    ├── test_pipeline.py                          # (existing)
    ├── test_models.py                            # DB model tests
    ├── test_schemas.py                           # Schema validation tests
    ├── test_bathymetry_service.py                # Bathymetry service tests
    ├── test_api_simulations.py                   # Simulation CRUD API tests
    ├── test_api_focus_zones.py                   # Focus zone API tests
    ├── test_api_run.py                           # Run coarse/detail API tests
    └── test_api_websocket.py                     # WebSocket tests
```

---

### Task 1: Dependencies and Config

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/src/tsunami/config.py`

- [ ] **Step 1: Update pyproject.toml with new dependencies**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "tsunami"
version = "0.1.0"
description = "Tsunami simulation engine"
requires-python = ">=3.12"
dependencies = [
    "numpy>=1.26",
    "scipy>=1.12",
    "xarray>=2024.1",
    "netcdf4>=1.6",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "sqlalchemy>=2.0",
    "aiosqlite>=0.20",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "celery[redis]>=5.4",
    "redis>=5.0",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.0",
    "pytest-asyncio>=0.24",
    "anyio>=4.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/tsunami"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Install updated dependencies**

```bash
cd backend && pip install -e ".[dev]"
```

Expected: Successful install with FastAPI, SQLAlchemy, Celery, etc.

- [ ] **Step 3: Write failing test for config**

`backend/tests/test_config.py`:
```python
from tsunami.config import Settings


class TestSettings:
    def test_default_settings(self):
        settings = Settings()
        assert settings.database_url.endswith("tsunami.db")
        assert settings.data_dir.endswith("data")
        assert settings.redis_url == "redis://localhost:6379/0"

    def test_results_dir_under_data(self):
        settings = Settings()
        assert "results" in settings.results_dir
```

- [ ] **Step 4: Run test to verify it fails**

```bash
cd backend && pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'tsunami.config'`

- [ ] **Step 5: Implement config module**

`backend/src/tsunami/config.py`:
```python
"""Application settings via pydantic-settings."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    data_dir: str = ""
    results_dir: str = ""
    bathymetry_cache_dir: str = ""
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = {"env_prefix": "TSUNAMI_"}

    def model_post_init(self, __context):
        base = Path(__file__).resolve().parent.parent.parent.parent  # backend/
        if not self.data_dir:
            self.data_dir = str(base / "data")
        if not self.results_dir:
            self.results_dir = str(Path(self.data_dir) / "results")
        if not self.bathymetry_cache_dir:
            self.bathymetry_cache_dir = str(Path(self.data_dir) / "bathymetry")
        if not self.database_url:
            self.database_url = f"sqlite+aiosqlite:///{Path(self.data_dir) / 'tsunami.db'}"
        # Ensure directories exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.bathymetry_cache_dir, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd backend && pytest tests/test_config.py -v
```

Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/src/tsunami/config.py backend/tests/test_config.py
git commit -m "feat: add app config with pydantic-settings and updated dependencies"
```

---

### Task 2: Database Models

**Files:**
- Create: `backend/src/tsunami/database.py`
- Create: `backend/src/tsunami/models.py`
- Create: `backend/tests/test_models.py`

- [ ] **Step 1: Write failing tests for models**

`backend/tests/test_models.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tsunami.database import Base
from tsunami.models import Simulation, FocusZone, SimulationStatus, ZoneStatus, ZoneSource


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


class TestSimulationModel:
    def test_create_simulation(self, db):
        sim = Simulation(
            name="Test Sim",
            earthquake_lat=0.0,
            earthquake_lon=100.0,
            earthquake_magnitude=8.0,
            earthquake_direction=270.0,
            earthquake_depth_km=15.0,
            grid_resolution_km=2.0,
            duration_hours=6.0,
        )
        db.add(sim)
        db.commit()
        db.refresh(sim)
        assert sim.id is not None
        assert sim.status == SimulationStatus.PENDING
        assert sim.name == "Test Sim"

    def test_simulation_default_status(self, db):
        sim = Simulation(
            name="Defaults",
            earthquake_lat=0.0,
            earthquake_lon=100.0,
            earthquake_magnitude=7.0,
            earthquake_direction=0.0,
            earthquake_depth_km=10.0,
        )
        db.add(sim)
        db.commit()
        db.refresh(sim)
        assert sim.status == SimulationStatus.PENDING
        assert sim.grid_resolution_km == 2.0
        assert sim.duration_hours == 6.0


class TestFocusZoneModel:
    def test_create_focus_zone(self, db):
        sim = Simulation(
            name="Parent",
            earthquake_lat=0.0,
            earthquake_lon=100.0,
            earthquake_magnitude=8.0,
            earthquake_direction=270.0,
            earthquake_depth_km=15.0,
        )
        db.add(sim)
        db.commit()

        zone = FocusZone(
            simulation_id=sim.id,
            name="Zone 1",
            lat_min=-1.0,
            lat_max=1.0,
            lon_min=99.0,
            lon_max=101.0,
            source=ZoneSource.AUTO,
            grid_resolution_m=100.0,
        )
        db.add(zone)
        db.commit()
        db.refresh(zone)
        assert zone.id is not None
        assert zone.status == ZoneStatus.PENDING
        assert zone.simulation_id == sim.id

    def test_simulation_has_zones(self, db):
        sim = Simulation(
            name="With Zones",
            earthquake_lat=0.0,
            earthquake_lon=100.0,
            earthquake_magnitude=8.0,
            earthquake_direction=270.0,
            earthquake_depth_km=15.0,
        )
        db.add(sim)
        db.commit()

        z1 = FocusZone(
            simulation_id=sim.id, name="Z1",
            lat_min=-1.0, lat_max=1.0, lon_min=99.0, lon_max=101.0,
            source=ZoneSource.USER, grid_resolution_m=100.0,
        )
        z2 = FocusZone(
            simulation_id=sim.id, name="Z2",
            lat_min=-2.0, lat_max=0.0, lon_min=98.0, lon_max=100.0,
            source=ZoneSource.PRESET, grid_resolution_m=50.0,
        )
        db.add_all([z1, z2])
        db.commit()
        db.refresh(sim)
        assert len(sim.focus_zones) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'tsunami.database'`

- [ ] **Step 3: Implement database module**

`backend/src/tsunami/database.py`:
```python
"""SQLAlchemy engine, session factory, and Base."""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from tsunami.config import get_settings


class Base(DeclarativeBase):
    pass


def get_sync_engine():
    url = get_settings().database_url.replace("sqlite+aiosqlite", "sqlite")
    return create_engine(url)


def get_async_engine():
    return create_async_engine(get_settings().database_url)


def get_async_session_factory():
    return async_sessionmaker(get_async_engine(), expire_on_commit=False)
```

- [ ] **Step 4: Implement models**

`backend/src/tsunami/models.py`:
```python
"""SQLAlchemy ORM models for simulation metadata."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tsunami.database import Base


class SimulationStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING_COARSE = "running_coarse"
    COARSE_COMPLETE = "coarse_complete"
    RUNNING_DETAIL = "running_detail"
    COMPLETE = "complete"
    FAILED = "failed"


class ZoneStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class ZoneSource(str, enum.Enum):
    AUTO = "auto"
    PRESET = "preset"
    USER = "user"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Simulation(Base):
    __tablename__ = "simulations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(36), default=_uuid, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[SimulationStatus] = mapped_column(
        Enum(SimulationStatus), default=SimulationStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Earthquake source
    earthquake_lat: Mapped[float] = mapped_column(Float)
    earthquake_lon: Mapped[float] = mapped_column(Float)
    earthquake_magnitude: Mapped[float] = mapped_column(Float)
    earthquake_direction: Mapped[float] = mapped_column(Float, default=0.0)
    earthquake_depth_km: Mapped[float] = mapped_column(Float, default=15.0)

    # Advanced fault params (nullable)
    fault_strike: Mapped[float | None] = mapped_column(Float, nullable=True)
    fault_dip: Mapped[float | None] = mapped_column(Float, nullable=True)
    fault_rake: Mapped[float | None] = mapped_column(Float, nullable=True)
    fault_slip_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    fault_length_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    fault_width_km: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Coarse config
    grid_resolution_km: Mapped[float] = mapped_column(Float, default=2.0)
    duration_hours: Mapped[float] = mapped_column(Float, default=6.0)

    # Result file paths (nullable, populated after run)
    coarse_result_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_heights_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    impacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    focus_zones: Mapped[list["FocusZone"]] = relationship(
        back_populates="simulation", cascade="all, delete-orphan"
    )


class FocusZone(Base):
    __tablename__ = "focus_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(36), default=_uuid, unique=True, index=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[ZoneStatus] = mapped_column(Enum(ZoneStatus), default=ZoneStatus.PENDING)
    source: Mapped[ZoneSource] = mapped_column(Enum(ZoneSource))

    lat_min: Mapped[float] = mapped_column(Float)
    lat_max: Mapped[float] = mapped_column(Float)
    lon_min: Mapped[float] = mapped_column(Float)
    lon_max: Mapped[float] = mapped_column(Float)
    grid_resolution_m: Mapped[float] = mapped_column(Float, default=100.0)

    # Result file paths
    inundation_geojson_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    flood_depth_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_runup_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    simulation: Mapped["Simulation"] = relationship(back_populates="focus_zones")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_models.py -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/src/tsunami/database.py backend/src/tsunami/models.py backend/tests/test_models.py
git commit -m "feat: add SQLAlchemy models for Simulation and FocusZone"
```

---

### Task 3: Pydantic Schemas

**Files:**
- Create: `backend/src/tsunami/schemas.py`
- Create: `backend/tests/test_schemas.py`

- [ ] **Step 1: Write failing tests for schemas**

`backend/tests/test_schemas.py`:
```python
import pytest
from pydantic import ValidationError
from tsunami.schemas import (
    SimulationCreate,
    SimulationRead,
    FocusZoneCreate,
    FocusZoneRead,
    CoarseResultRead,
)


class TestSimulationCreate:
    def test_valid_simple_mode(self):
        s = SimulationCreate(
            name="Test",
            earthquake_lat=0.0,
            earthquake_lon=100.0,
            earthquake_magnitude=8.0,
            earthquake_direction=270.0,
        )
        assert s.earthquake_magnitude == 8.0
        assert s.earthquake_depth_km == 15.0  # default

    def test_invalid_magnitude(self):
        with pytest.raises(ValidationError):
            SimulationCreate(
                name="Bad",
                earthquake_lat=0.0,
                earthquake_lon=100.0,
                earthquake_magnitude=15.0,  # too high
                earthquake_direction=0.0,
            )

    def test_invalid_lat(self):
        with pytest.raises(ValidationError):
            SimulationCreate(
                name="Bad",
                earthquake_lat=100.0,  # out of range
                earthquake_lon=0.0,
                earthquake_magnitude=7.0,
                earthquake_direction=0.0,
            )


class TestFocusZoneCreate:
    def test_valid_zone(self):
        z = FocusZoneCreate(
            name="Zone 1",
            lat_min=-1.0,
            lat_max=1.0,
            lon_min=99.0,
            lon_max=101.0,
            source="user",
        )
        assert z.grid_resolution_m == 100.0  # default

    def test_invalid_bounds(self):
        with pytest.raises(ValidationError):
            FocusZoneCreate(
                name="Bad",
                lat_min=5.0,
                lat_max=1.0,  # min > max
                lon_min=99.0,
                lon_max=101.0,
                source="user",
            )


class TestSimulationRead:
    def test_from_dict(self):
        data = {
            "uid": "abc-123",
            "name": "Test",
            "status": "pending",
            "created_at": "2026-01-01T00:00:00Z",
            "earthquake_lat": 0.0,
            "earthquake_lon": 100.0,
            "earthquake_magnitude": 8.0,
            "earthquake_direction": 270.0,
            "earthquake_depth_km": 15.0,
            "grid_resolution_km": 2.0,
            "duration_hours": 6.0,
            "focus_zones": [],
        }
        s = SimulationRead(**data)
        assert s.uid == "abc-123"
        assert s.status == "pending"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_schemas.py -v
```

Expected: `ModuleNotFoundError: No module named 'tsunami.schemas'`

- [ ] **Step 3: Implement schemas**

`backend/src/tsunami/schemas.py`:
```python
"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from pydantic import BaseModel, Field, model_validator


class SimulationCreate(BaseModel):
    name: str = Field(max_length=200)
    earthquake_lat: float = Field(ge=-90.0, le=90.0)
    earthquake_lon: float = Field(ge=-180.0, le=180.0)
    earthquake_magnitude: float = Field(ge=5.0, le=10.0)
    earthquake_direction: float = Field(ge=0.0, lt=360.0, default=0.0)
    earthquake_depth_km: float = Field(ge=0.0, le=700.0, default=15.0)
    grid_resolution_km: float = Field(gt=0.0, default=2.0)
    duration_hours: float = Field(gt=0.0, le=48.0, default=6.0)

    # Advanced fault params (optional)
    fault_strike: float | None = None
    fault_dip: float | None = None
    fault_rake: float | None = None
    fault_slip_m: float | None = None
    fault_length_km: float | None = None
    fault_width_km: float | None = None


class FocusZoneCreate(BaseModel):
    name: str = Field(max_length=200)
    lat_min: float = Field(ge=-90.0, le=90.0)
    lat_max: float = Field(ge=-90.0, le=90.0)
    lon_min: float = Field(ge=-180.0, le=180.0)
    lon_max: float = Field(ge=-180.0, le=180.0)
    source: str = Field(pattern=r"^(auto|preset|user)$")
    grid_resolution_m: float = Field(gt=0.0, default=100.0)

    @model_validator(mode="after")
    def check_bounds(self):
        if self.lat_min >= self.lat_max:
            raise ValueError("lat_min must be less than lat_max")
        if self.lon_min >= self.lon_max:
            raise ValueError("lon_min must be less than lon_max")
        return self


class FocusZoneUpdate(BaseModel):
    name: str | None = Field(max_length=200, default=None)
    lat_min: float | None = Field(ge=-90.0, le=90.0, default=None)
    lat_max: float | None = Field(ge=-90.0, le=90.0, default=None)
    lon_min: float | None = Field(ge=-180.0, le=180.0, default=None)
    lon_max: float | None = Field(ge=-180.0, le=180.0, default=None)
    grid_resolution_m: float | None = Field(gt=0.0, default=None)


class FocusZoneRead(BaseModel):
    uid: str
    name: str
    status: str
    source: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    grid_resolution_m: float
    max_runup_m: float | None = None

    model_config = {"from_attributes": True}


class SimulationRead(BaseModel):
    uid: str
    name: str
    status: str
    created_at: datetime
    earthquake_lat: float
    earthquake_lon: float
    earthquake_magnitude: float
    earthquake_direction: float
    earthquake_depth_km: float
    grid_resolution_km: float
    duration_hours: float
    focus_zones: list[FocusZoneRead] = []

    model_config = {"from_attributes": True}


class CoarseResultRead(BaseModel):
    status: str
    impacts: list[dict] = []
    suggested_zones: list[dict] = []
    max_wave_height: float | None = None


class DetailResultRead(BaseModel):
    zone_uid: str
    status: str
    max_runup_m: float | None = None
    inundation_geojson: dict | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_schemas.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/schemas.py backend/tests/test_schemas.py
git commit -m "feat: add Pydantic schemas for API request/response validation"
```

---

### Task 4: Bathymetry Service

**Files:**
- Create: `backend/src/tsunami/bathymetry/service.py`
- Create: `backend/tests/test_bathymetry_service.py`

The bathymetry service provides a unified interface: fetch real data if available, fall back to procedural generation.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_bathymetry_service.py`:
```python
import numpy as np
import pytest
from tsunami.simulation.grid import create_grid
from tsunami.bathymetry.service import BathymetryService


class TestBathymetryService:
    def test_get_bathymetry_procedural_fallback(self):
        service = BathymetryService(cache_dir="/tmp/tsunami_bathy_test")
        grid = create_grid(
            lat_min=-2.0, lat_max=2.0,
            lon_min=98.0, lon_max=102.0,
            resolution_km=50.0,
        )
        result = service.get_bathymetry(grid, source="procedural")
        assert result.shape == grid.depth.shape
        assert np.any(result > 0)  # should have some ocean depth

    def test_check_availability_procedural_always_available(self):
        service = BathymetryService(cache_dir="/tmp/tsunami_bathy_test")
        avail = service.check_availability(
            lat_min=-2.0, lat_max=2.0, lon_min=98.0, lon_max=102.0,
        )
        assert avail["procedural"] is True

    def test_get_bathymetry_returns_correct_shape(self):
        service = BathymetryService(cache_dir="/tmp/tsunami_bathy_test")
        grid = create_grid(
            lat_min=0.0, lat_max=1.0,
            lon_min=0.0, lon_max=1.0,
            resolution_km=20.0,
        )
        result = service.get_bathymetry(grid, source="procedural")
        assert result.shape == grid.depth.shape
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_bathymetry_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'tsunami.bathymetry.service'`

- [ ] **Step 3: Implement bathymetry service**

`backend/src/tsunami/bathymetry/service.py`:
```python
"""Unified bathymetry data service.

Provides ocean depth data from multiple sources with procedural fallback.
GEBCO/ETOPO integration is a future enhancement — currently uses procedural
generation which is sufficient for demos and testing.
"""

from pathlib import Path
import numpy as np

from tsunami.simulation.grid import Grid
from tsunami.bathymetry.procedural import generate_procedural_bathymetry


class BathymetryService:
    def __init__(self, cache_dir: str = "/tmp/tsunami_bathy"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def check_availability(
        self, lat_min: float, lat_max: float, lon_min: float, lon_max: float,
    ) -> dict[str, bool]:
        """Check which bathymetry sources are available for the given bounds."""
        return {
            "gebco": False,  # Not yet implemented
            "etopo": False,  # Not yet implemented
            "procedural": True,
        }

    def get_bathymetry(
        self, grid: Grid, source: str = "procedural",
    ) -> np.ndarray:
        """Fetch bathymetry data for the given grid.

        Args:
            grid: Target grid to fill with depth values.
            source: Data source — "gebco", "etopo", or "procedural".

        Returns:
            2D array of ocean depth values (positive = below sea level).
        """
        if source == "procedural":
            return self._get_procedural(grid)
        # Future: GEBCO/ETOPO fetchers
        raise ValueError(f"Unknown bathymetry source: {source}. Available: procedural")

    def _get_procedural(self, grid: Grid) -> np.ndarray:
        """Generate procedural bathymetry for the grid."""
        result_grid = generate_procedural_bathymetry(grid)
        return result_grid.depth
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_bathymetry_service.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/bathymetry/service.py backend/tests/test_bathymetry_service.py
git commit -m "feat: add unified bathymetry service with procedural fallback"
```

---

### Task 5: FastAPI App and Dependencies

**Files:**
- Create: `backend/src/tsunami/app.py`
- Create: `backend/src/tsunami/api/__init__.py`
- Create: `backend/src/tsunami/api/deps.py`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Write failing test for app creation**

Add to `backend/tests/conftest.py` (keep existing fixtures):
```python
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
def app(tmp_path):
    """Create a test FastAPI app with a temporary database."""
    import os
    os.environ["TSUNAMI_DATA_DIR"] = str(tmp_path / "data")
    os.environ["TSUNAMI_DATABASE_URL"] = f"sqlite:///{tmp_path / 'test.db'}"
    from tsunami.config import get_settings
    get_settings.cache_clear()
    application = create_app()
    return application


@pytest.fixture
async def client(app):
    """Async test client for the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
```

`backend/tests/test_app.py`:
```python
import pytest


class TestAppCreation:
    @pytest.mark.anyio
    async def test_health_endpoint(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_app.py -v
```

Expected: `ModuleNotFoundError: No module named 'tsunami.app'`

- [ ] **Step 3: Implement app factory and deps**

`backend/src/tsunami/api/__init__.py`:
```python
"""API package."""
```

`backend/src/tsunami/api/deps.py`:
```python
"""FastAPI dependency injection."""

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tsunami.config import get_settings

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url)
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _get_session_factory()() as session:
        yield session


def reset_engine():
    """Reset engine/session factory — used in tests."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
```

`backend/src/tsunami/app.py`:
```python
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

    # Route registration will happen in later tasks
    from tsunami.api import simulations, focus_zones, run, export, bathymetry_routes, presets
    app.include_router(simulations.router, prefix="/api")
    app.include_router(focus_zones.router, prefix="/api")
    app.include_router(run.router, prefix="/api")
    app.include_router(export.router, prefix="/api")
    app.include_router(bathymetry_routes.router, prefix="/api")
    app.include_router(presets.router, prefix="/api")

    return app
```

Note: The route modules don't exist yet, so we need stub files for them to avoid import errors:

`backend/src/tsunami/api/simulations.py`:
```python
from fastapi import APIRouter
router = APIRouter()
```

`backend/src/tsunami/api/focus_zones.py`:
```python
from fastapi import APIRouter
router = APIRouter()
```

`backend/src/tsunami/api/run.py`:
```python
from fastapi import APIRouter
router = APIRouter()
```

`backend/src/tsunami/api/export.py`:
```python
from fastapi import APIRouter
router = APIRouter()
```

`backend/src/tsunami/api/bathymetry_routes.py`:
```python
from fastapi import APIRouter
router = APIRouter()
```

`backend/src/tsunami/api/presets.py`:
```python
from fastapi import APIRouter
router = APIRouter()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_app.py -v
```

Expected: PASS

- [ ] **Step 5: Verify existing tests still pass**

```bash
cd backend && pytest tests/ -v --ignore=tests/test_app.py -x
```

Expected: All 44 existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/src/tsunami/app.py backend/src/tsunami/api/ backend/tests/conftest.py backend/tests/test_app.py
git commit -m "feat: add FastAPI app factory with health endpoint and test client"
```

---

### Task 6: Simulation CRUD API

**Files:**
- Modify: `backend/src/tsunami/api/simulations.py`
- Create: `backend/tests/test_api_simulations.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/test_api_simulations.py`:
```python
import pytest


class TestCreateSimulation:
    @pytest.mark.anyio
    async def test_create_simulation(self, client):
        resp = await client.post("/api/simulations", json={
            "name": "Tohoku 2011",
            "earthquake_lat": 38.3,
            "earthquake_lon": 142.4,
            "earthquake_magnitude": 9.1,
            "earthquake_direction": 290.0,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Tohoku 2011"
        assert data["status"] == "pending"
        assert "uid" in data

    @pytest.mark.anyio
    async def test_create_simulation_validation_error(self, client):
        resp = await client.post("/api/simulations", json={
            "name": "Bad",
            "earthquake_lat": 0.0,
            "earthquake_lon": 0.0,
            "earthquake_magnitude": 20.0,  # invalid
            "earthquake_direction": 0.0,
        })
        assert resp.status_code == 422


class TestListSimulations:
    @pytest.mark.anyio
    async def test_list_empty(self, client):
        resp = await client.get("/api/simulations")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.anyio
    async def test_list_after_create(self, client):
        await client.post("/api/simulations", json={
            "name": "Sim 1",
            "earthquake_lat": 0.0, "earthquake_lon": 100.0,
            "earthquake_magnitude": 8.0, "earthquake_direction": 270.0,
        })
        resp = await client.get("/api/simulations")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestGetSimulation:
    @pytest.mark.anyio
    async def test_get_by_uid(self, client):
        create_resp = await client.post("/api/simulations", json={
            "name": "Get Test",
            "earthquake_lat": 0.0, "earthquake_lon": 100.0,
            "earthquake_magnitude": 7.5, "earthquake_direction": 0.0,
        })
        uid = create_resp.json()["uid"]
        resp = await client.get(f"/api/simulations/{uid}")
        assert resp.status_code == 200
        assert resp.json()["uid"] == uid

    @pytest.mark.anyio
    async def test_get_not_found(self, client):
        resp = await client.get("/api/simulations/nonexistent")
        assert resp.status_code == 404


class TestDeleteSimulation:
    @pytest.mark.anyio
    async def test_delete(self, client):
        create_resp = await client.post("/api/simulations", json={
            "name": "Delete Me",
            "earthquake_lat": 0.0, "earthquake_lon": 100.0,
            "earthquake_magnitude": 7.0, "earthquake_direction": 0.0,
        })
        uid = create_resp.json()["uid"]
        resp = await client.delete(f"/api/simulations/{uid}")
        assert resp.status_code == 204
        get_resp = await client.get(f"/api/simulations/{uid}")
        assert get_resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_api_simulations.py -v
```

Expected: 404 on POST /api/simulations (empty router)

- [ ] **Step 3: Implement simulation CRUD routes**

`backend/src/tsunami/api/simulations.py`:
```python
"""Simulation CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tsunami.api.deps import get_db
from tsunami.models import Simulation
from tsunami.schemas import SimulationCreate, SimulationRead

router = APIRouter(tags=["simulations"])


@router.post("/simulations", response_model=SimulationRead, status_code=status.HTTP_201_CREATED)
async def create_simulation(body: SimulationCreate, db: AsyncSession = Depends(get_db)):
    sim = Simulation(**body.model_dump())
    db.add(sim)
    await db.commit()
    await db.refresh(sim, attribute_names=["focus_zones"])
    return sim


@router.get("/simulations", response_model=list[SimulationRead])
async def list_simulations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Simulation).options(selectinload(Simulation.focus_zones)).order_by(Simulation.created_at.desc())
    )
    return result.scalars().all()


@router.get("/simulations/{uid}", response_model=SimulationRead)
async def get_simulation(uid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Simulation).options(selectinload(Simulation.focus_zones)).where(Simulation.uid == uid)
    )
    sim = result.scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return sim


@router.delete("/simulations/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_simulation(uid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Simulation).where(Simulation.uid == uid))
    sim = result.scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    await db.delete(sim)
    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_api_simulations.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/api/simulations.py backend/tests/test_api_simulations.py
git commit -m "feat: add simulation CRUD API endpoints"
```

---

### Task 7: Focus Zone API

**Files:**
- Modify: `backend/src/tsunami/api/focus_zones.py`
- Create: `backend/tests/test_api_focus_zones.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/test_api_focus_zones.py`:
```python
import pytest


@pytest.fixture
async def sim_uid(client):
    resp = await client.post("/api/simulations", json={
        "name": "Zone Parent",
        "earthquake_lat": 0.0, "earthquake_lon": 100.0,
        "earthquake_magnitude": 8.0, "earthquake_direction": 270.0,
    })
    return resp.json()["uid"]


class TestAddFocusZone:
    @pytest.mark.anyio
    async def test_add_zone(self, client, sim_uid):
        resp = await client.post(f"/api/simulations/{sim_uid}/focus-zones", json={
            "name": "Zone 1",
            "lat_min": -1.0, "lat_max": 1.0,
            "lon_min": 99.0, "lon_max": 101.0,
            "source": "user",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Zone 1"
        assert data["status"] == "pending"

    @pytest.mark.anyio
    async def test_add_zone_to_nonexistent_sim(self, client):
        resp = await client.post("/api/simulations/bad-uid/focus-zones", json={
            "name": "Zone 1",
            "lat_min": -1.0, "lat_max": 1.0,
            "lon_min": 99.0, "lon_max": 101.0,
            "source": "user",
        })
        assert resp.status_code == 404


class TestListFocusZones:
    @pytest.mark.anyio
    async def test_list_zones(self, client, sim_uid):
        await client.post(f"/api/simulations/{sim_uid}/focus-zones", json={
            "name": "Z1", "lat_min": -1.0, "lat_max": 1.0,
            "lon_min": 99.0, "lon_max": 101.0, "source": "user",
        })
        resp = await client.get(f"/api/simulations/{sim_uid}/focus-zones")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestUpdateFocusZone:
    @pytest.mark.anyio
    async def test_update_zone_name(self, client, sim_uid):
        create_resp = await client.post(f"/api/simulations/{sim_uid}/focus-zones", json={
            "name": "Old Name", "lat_min": -1.0, "lat_max": 1.0,
            "lon_min": 99.0, "lon_max": 101.0, "source": "user",
        })
        zone_uid = create_resp.json()["uid"]
        resp = await client.put(
            f"/api/simulations/{sim_uid}/focus-zones/{zone_uid}",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"


class TestDeleteFocusZone:
    @pytest.mark.anyio
    async def test_delete_zone(self, client, sim_uid):
        create_resp = await client.post(f"/api/simulations/{sim_uid}/focus-zones", json={
            "name": "Bye", "lat_min": -1.0, "lat_max": 1.0,
            "lon_min": 99.0, "lon_max": 101.0, "source": "user",
        })
        zone_uid = create_resp.json()["uid"]
        resp = await client.delete(f"/api/simulations/{sim_uid}/focus-zones/{zone_uid}")
        assert resp.status_code == 204
        list_resp = await client.get(f"/api/simulations/{sim_uid}/focus-zones")
        assert len(list_resp.json()) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_api_focus_zones.py -v
```

Expected: 405 Method Not Allowed or 404 (empty router)

- [ ] **Step 3: Implement focus zone routes**

`backend/src/tsunami/api/focus_zones.py`:
```python
"""Focus zone CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tsunami.api.deps import get_db
from tsunami.models import FocusZone, Simulation, ZoneSource
from tsunami.schemas import FocusZoneCreate, FocusZoneRead, FocusZoneUpdate

router = APIRouter(tags=["focus-zones"])


async def _get_simulation(uid: str, db: AsyncSession) -> Simulation:
    result = await db.execute(select(Simulation).where(Simulation.uid == uid))
    sim = result.scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return sim


@router.post(
    "/simulations/{sim_uid}/focus-zones",
    response_model=FocusZoneRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_focus_zone(
    sim_uid: str, body: FocusZoneCreate, db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation(sim_uid, db)
    zone = FocusZone(
        simulation_id=sim.id,
        name=body.name,
        lat_min=body.lat_min,
        lat_max=body.lat_max,
        lon_min=body.lon_min,
        lon_max=body.lon_max,
        source=ZoneSource(body.source),
        grid_resolution_m=body.grid_resolution_m,
    )
    db.add(zone)
    await db.commit()
    await db.refresh(zone)
    return zone


@router.get("/simulations/{sim_uid}/focus-zones", response_model=list[FocusZoneRead])
async def list_focus_zones(sim_uid: str, db: AsyncSession = Depends(get_db)):
    sim = await _get_simulation(sim_uid, db)
    result = await db.execute(
        select(FocusZone).where(FocusZone.simulation_id == sim.id)
    )
    return result.scalars().all()


@router.put(
    "/simulations/{sim_uid}/focus-zones/{zone_uid}",
    response_model=FocusZoneRead,
)
async def update_focus_zone(
    sim_uid: str, zone_uid: str, body: FocusZoneUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _get_simulation(sim_uid, db)
    result = await db.execute(select(FocusZone).where(FocusZone.uid == zone_uid))
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail="Focus zone not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(zone, field, value)
    await db.commit()
    await db.refresh(zone)
    return zone


@router.delete(
    "/simulations/{sim_uid}/focus-zones/{zone_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_focus_zone(
    sim_uid: str, zone_uid: str, db: AsyncSession = Depends(get_db),
):
    await _get_simulation(sim_uid, db)
    result = await db.execute(select(FocusZone).where(FocusZone.uid == zone_uid))
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail="Focus zone not found")
    await db.delete(zone)
    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_api_focus_zones.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/api/focus_zones.py backend/tests/test_api_focus_zones.py
git commit -m "feat: add focus zone CRUD API endpoints"
```

---

### Task 8: Coarse Simulation Run Endpoint

**Files:**
- Modify: `backend/src/tsunami/api/run.py`
- Create: `backend/tests/test_api_run.py`

The coarse SWE simulation runs in-process (not Celery) for interactive speed. It updates simulation status and stores results.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_api_run.py`:
```python
import pytest


@pytest.fixture
async def sim_uid(client):
    resp = await client.post("/api/simulations", json={
        "name": "Run Test",
        "earthquake_lat": 0.0, "earthquake_lon": 100.0,
        "earthquake_magnitude": 7.5, "earthquake_direction": 270.0,
        "grid_resolution_km": 50.0,  # coarse for speed
        "duration_hours": 0.5,  # 30 minutes
    })
    return resp.json()["uid"]


class TestRunCoarse:
    @pytest.mark.anyio
    async def test_run_coarse_starts_and_completes(self, client, sim_uid):
        resp = await client.post(f"/api/simulations/{sim_uid}/run-coarse")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "coarse_complete"
        assert "impacts" in data

    @pytest.mark.anyio
    async def test_run_coarse_updates_simulation_status(self, client, sim_uid):
        await client.post(f"/api/simulations/{sim_uid}/run-coarse")
        resp = await client.get(f"/api/simulations/{sim_uid}")
        assert resp.json()["status"] == "coarse_complete"

    @pytest.mark.anyio
    async def test_run_coarse_nonexistent_sim(self, client):
        resp = await client.post("/api/simulations/bad-uid/run-coarse")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_get_coarse_result(self, client, sim_uid):
        await client.post(f"/api/simulations/{sim_uid}/run-coarse")
        resp = await client.get(f"/api/simulations/{sim_uid}/coarse-result")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "coarse_complete"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_api_run.py -v
```

Expected: 405 or 404 (empty router)

- [ ] **Step 3: Implement run endpoints**

`backend/src/tsunami/api/run.py`:
```python
"""Simulation execution endpoints."""

import json
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tsunami.api.deps import get_db
from tsunami.bathymetry.service import BathymetryService
from tsunami.config import get_settings
from tsunami.models import Simulation, SimulationStatus
from tsunami.schemas import CoarseResultRead
from tsunami.simulation.grid import create_grid, domain_for_magnitude
from tsunami.simulation.impact import detect_coastal_impacts, suggest_focus_zones
from tsunami.simulation.okada import magnitude_to_fault_params, compute_displacement
from tsunami.simulation.swe_solver import SWESolverConfig, SWEState, run_swe

router = APIRouter(tags=["run"])


@router.post("/simulations/{uid}/run-coarse")
async def run_coarse(uid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Simulation).where(Simulation.uid == uid))
    sim = result.scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")

    # Update status
    sim.status = SimulationStatus.RUNNING_COARSE
    await db.commit()

    try:
        # 1. Create grid
        bounds = domain_for_magnitude(
            sim.earthquake_lat, sim.earthquake_lon, sim.earthquake_magnitude,
        )
        grid = create_grid(
            lat_min=bounds["lat_min"], lat_max=bounds["lat_max"],
            lon_min=bounds["lon_min"], lon_max=bounds["lon_max"],
            resolution_km=sim.grid_resolution_km,
        )

        # 2. Get bathymetry
        bathy_service = BathymetryService(
            cache_dir=get_settings().bathymetry_cache_dir,
        )
        depth = bathy_service.get_bathymetry(grid, source="procedural")
        grid = grid.with_depth(depth)

        # 3. Compute displacement
        fault = magnitude_to_fault_params(
            sim.earthquake_lat, sim.earthquake_lon,
            sim.earthquake_magnitude, sim.earthquake_direction,
        )
        displacement = compute_displacement(fault, grid)

        # 4. Run SWE
        config = SWESolverConfig(
            duration_seconds=sim.duration_hours * 3600,
            output_interval_seconds=max(300.0, sim.duration_hours * 3600 / 20),
            cfl=0.4,
        )
        frames: list[tuple[float, SWEState]] = []

        def save_frame(t: float, state: SWEState):
            frames.append((t, SWEState(
                eta=state.eta.copy(), hu=state.hu.copy(), hv=state.hv.copy(),
            )))

        run_swe(grid, displacement, config, frame_callback=save_frame)

        # 5. Compute max heights and detect impacts
        max_heights = np.zeros(grid.depth.shape)
        for _, state in frames:
            np.maximum(max_heights, np.abs(state.eta), out=max_heights)

        impacts = detect_coastal_impacts(
            grid, max_heights, depth_threshold=300.0, height_threshold=0.1,
        )
        zones = suggest_focus_zones(impacts, cluster_radius_km=200.0)

        # 6. Save results
        results_dir = Path(get_settings().results_dir) / sim.uid
        results_dir.mkdir(parents=True, exist_ok=True)

        np.save(str(results_dir / "max_heights.npy"), max_heights)

        impacts_data = [
            {"lat": imp.lat, "lon": imp.lon, "max_height": imp.max_height,
             "arrival_time_s": imp.arrival_time_s}
            for imp in impacts
        ]
        zones_data = [
            {"lat_min": z.lat_min, "lat_max": z.lat_max,
             "lon_min": z.lon_min, "lon_max": z.lon_max,
             "max_impact_height": z.max_impact_height,
             "impact_count": z.impact_count}
            for z in zones
        ]

        sim.impacts_json = json.dumps({"impacts": impacts_data, "zones": zones_data})
        sim.coarse_result_path = str(results_dir)
        sim.status = SimulationStatus.COARSE_COMPLETE
        await db.commit()

        return {
            "status": "coarse_complete",
            "impacts": impacts_data,
            "suggested_zones": zones_data,
            "max_wave_height": float(np.max(max_heights)),
        }

    except Exception as e:
        sim.status = SimulationStatus.FAILED
        sim.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/simulations/{uid}/coarse-result", response_model=CoarseResultRead)
async def get_coarse_result(uid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Simulation).where(Simulation.uid == uid))
    sim = result.scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")

    impacts_data = json.loads(sim.impacts_json) if sim.impacts_json else {"impacts": [], "zones": []}

    max_wave_height = None
    if sim.coarse_result_path:
        heights_path = Path(sim.coarse_result_path) / "max_heights.npy"
        if heights_path.exists():
            max_heights = np.load(str(heights_path))
            max_wave_height = float(np.max(max_heights))

    return CoarseResultRead(
        status=sim.status.value,
        impacts=impacts_data.get("impacts", []),
        suggested_zones=impacts_data.get("zones", []),
        max_wave_height=max_wave_height,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_api_run.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/api/run.py backend/tests/test_api_run.py
git commit -m "feat: add coarse simulation run endpoint with impact detection"
```

---

### Task 9: Celery Workers

**Files:**
- Create: `backend/src/tsunami/workers/__init__.py`
- Create: `backend/src/tsunami/workers/celery_app.py`
- Create: `backend/src/tsunami/workers/tasks.py`

The Celery worker handles Boussinesq (detail) simulation as background tasks. We test the task logic synchronously without requiring a running Redis.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_workers.py`:
```python
import json
import numpy as np
import pytest
from tsunami.workers.tasks import run_detail_zone_sync


class TestRunDetailZoneSync:
    def test_runs_boussinesq_and_returns_result(self, tmp_path):
        """Test the synchronous core of the detail task."""
        result = run_detail_zone_sync(
            lat_min=-0.5, lat_max=0.5,
            lon_min=-0.5, lon_max=0.5,
            grid_resolution_m=5000.0,  # coarse for speed (5 km)
            duration_seconds=120.0,
            results_dir=str(tmp_path),
        )
        assert result["status"] == "complete"
        assert result["max_runup_m"] is not None
        assert "inundation_geojson" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_workers.py -v
```

Expected: `ModuleNotFoundError: No module named 'tsunami.workers'`

- [ ] **Step 3: Implement worker modules**

`backend/src/tsunami/workers/__init__.py`:
```python
"""Celery worker package."""
```

`backend/src/tsunami/workers/celery_app.py`:
```python
"""Celery application instance."""

from celery import Celery

from tsunami.config import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "tsunami",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
    )
    app.autodiscover_tasks(["tsunami.workers"])
    return app


celery_app = create_celery_app()
```

`backend/src/tsunami/workers/tasks.py`:
```python
"""Celery task definitions for background simulation work."""

import json
from pathlib import Path

import numpy as np

from tsunami.bathymetry.service import BathymetryService
from tsunami.simulation.boussinesq import BoussinesqConfig, run_boussinesq
from tsunami.simulation.grid import create_grid
from tsunami.simulation.inundation import compute_inundation


def run_detail_zone_sync(
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    grid_resolution_m: float,
    duration_seconds: float,
    results_dir: str,
    boundary_conditions=None,
) -> dict:
    """Run Boussinesq detail simulation for a single focus zone.

    This is the synchronous core — called by the Celery task wrapper
    and directly in tests.
    """
    resolution_km = grid_resolution_m / 1000.0
    grid = create_grid(
        lat_min=lat_min, lat_max=lat_max,
        lon_min=lon_min, lon_max=lon_max,
        resolution_km=resolution_km,
    )

    bathy_service = BathymetryService()
    depth = bathy_service.get_bathymetry(grid, source="procedural")
    grid = grid.with_depth(depth)

    initial_eta = np.zeros(grid.depth.shape)

    config = BoussinesqConfig(
        duration_seconds=duration_seconds,
        output_interval_seconds=max(30.0, duration_seconds / 10),
        cfl=0.3,
    )

    result = run_boussinesq(
        grid, initial_eta, config,
        boundary_conditions=boundary_conditions,
    )

    # Compute inundation
    inundation = compute_inundation(grid, result.max_wave_heights, result.max_velocity)

    # Save results
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    geojson = inundation.inundation_extent_geojson()
    geojson_path = out_dir / "inundation.geojson"
    with open(geojson_path, "w") as f:
        json.dump(geojson, f)

    np.save(str(out_dir / "flood_depth.npy"), inundation.flood_depth)

    return {
        "status": "complete",
        "max_runup_m": inundation.max_runup_m,
        "inundation_geojson": geojson,
        "inundation_geojson_path": str(geojson_path),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_workers.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/tsunami/workers/ backend/tests/test_workers.py
git commit -m "feat: add Celery worker with Boussinesq detail simulation task"
```

---

### Task 10: Export and Preset Endpoints

**Files:**
- Modify: `backend/src/tsunami/api/export.py`
- Modify: `backend/src/tsunami/api/bathymetry_routes.py`
- Modify: `backend/src/tsunami/api/presets.py`
- Create: `backend/tests/test_api_export.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/test_api_export.py`:
```python
import pytest


class TestPresets:
    @pytest.mark.anyio
    async def test_list_preset_locations(self, client):
        resp = await client.get("/api/presets/locations")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "name" in data[0]
        assert "lat" in data[0]
        assert "lon" in data[0]


class TestBathymetryCheck:
    @pytest.mark.anyio
    async def test_check_availability(self, client):
        resp = await client.get(
            "/api/bathymetry/check",
            params={"lat_min": -2, "lat_max": 2, "lon_min": 98, "lon_max": 102},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["procedural"] is True


class TestExport:
    @pytest.mark.anyio
    async def test_export_nonexistent_sim(self, client):
        resp = await client.get("/api/simulations/bad-uid/export", params={"format": "geojson"})
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_export_before_run(self, client):
        create_resp = await client.post("/api/simulations", json={
            "name": "Export Test",
            "earthquake_lat": 0.0, "earthquake_lon": 100.0,
            "earthquake_magnitude": 7.0, "earthquake_direction": 0.0,
        })
        uid = create_resp.json()["uid"]
        resp = await client.get(f"/api/simulations/{uid}/export", params={"format": "geojson"})
        assert resp.status_code == 400  # no results yet
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_api_export.py -v
```

Expected: Failures (empty routers)

- [ ] **Step 3: Implement preset locations**

`backend/src/tsunami/api/presets.py`:
```python
"""Preset location endpoints."""

from fastapi import APIRouter

router = APIRouter(tags=["presets"])

PRESET_LOCATIONS = [
    {"name": "Tohoku, Japan", "lat": 38.3, "lon": 142.4, "magnitude": 9.1, "direction": 290.0},
    {"name": "Sumatra, Indonesia", "lat": 3.3, "lon": 95.9, "magnitude": 9.1, "direction": 340.0},
    {"name": "Chile (Maule)", "lat": -35.8, "lon": -72.7, "magnitude": 8.8, "direction": 280.0},
    {"name": "Alaska (1964)", "lat": 61.0, "lon": -147.5, "magnitude": 9.2, "direction": 210.0},
    {"name": "Cascadia (scenario)", "lat": 44.5, "lon": -125.0, "magnitude": 9.0, "direction": 260.0},
    {"name": "Lisbon (1755)", "lat": 36.0, "lon": -11.0, "magnitude": 8.7, "direction": 300.0},
]


@router.get("/presets/locations")
async def list_preset_locations():
    return PRESET_LOCATIONS
```

- [ ] **Step 4: Implement bathymetry check endpoint**

`backend/src/tsunami/api/bathymetry_routes.py`:
```python
"""Bathymetry data endpoints."""

from fastapi import APIRouter, Query

from tsunami.bathymetry.service import BathymetryService
from tsunami.config import get_settings

router = APIRouter(tags=["bathymetry"])


@router.get("/bathymetry/check")
async def check_bathymetry(
    lat_min: float = Query(...),
    lat_max: float = Query(...),
    lon_min: float = Query(...),
    lon_max: float = Query(...),
):
    service = BathymetryService(cache_dir=get_settings().bathymetry_cache_dir)
    return service.check_availability(lat_min, lat_max, lon_min, lon_max)
```

- [ ] **Step 5: Implement export endpoint**

`backend/src/tsunami/api/export.py`:
```python
"""Export endpoints for simulation results."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tsunami.api.deps import get_db
from tsunami.models import Simulation

router = APIRouter(tags=["export"])


@router.get("/simulations/{uid}/export")
async def export_results(
    uid: str,
    format: str = Query(..., pattern=r"^(geojson|csv|netcdf)$"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Simulation).where(Simulation.uid == uid))
    sim = result.scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")

    if not sim.coarse_result_path:
        raise HTTPException(status_code=400, detail="No results available — run simulation first")

    results_dir = Path(sim.coarse_result_path)

    if format == "geojson":
        if sim.impacts_json:
            return JSONResponse(content=json.loads(sim.impacts_json))
        raise HTTPException(status_code=400, detail="No impact data available")

    # CSV and NetCDF exports are future enhancements
    raise HTTPException(status_code=501, detail=f"Export format '{format}' not yet implemented")
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_api_export.py -v
```

Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/src/tsunami/api/export.py backend/src/tsunami/api/bathymetry_routes.py backend/src/tsunami/api/presets.py backend/tests/test_api_export.py
git commit -m "feat: add export, bathymetry check, and preset location endpoints"
```

---

### Task 11: WebSocket Handler

**Files:**
- Create: `backend/src/tsunami/api/websocket.py`
- Create: `backend/tests/test_api_websocket.py`
- Modify: `backend/src/tsunami/app.py` (register WS route)

- [ ] **Step 1: Write failing tests**

`backend/tests/test_api_websocket.py`:
```python
import pytest
from starlette.testclient import TestClient


class TestWebSocket:
    def test_websocket_connect_and_receive(self, app):
        """Test WebSocket connection and message format."""
        # Use sync TestClient for WebSocket testing
        with TestClient(app) as tc:
            # First create a simulation via REST
            resp = tc.post("/api/simulations", json={
                "name": "WS Test",
                "earthquake_lat": 0.0, "earthquake_lon": 100.0,
                "earthquake_magnitude": 7.0, "earthquake_direction": 0.0,
            })
            uid = resp.json()["uid"]

            with tc.websocket_connect(f"/api/ws/simulations/{uid}") as ws:
                data = ws.receive_json()
                assert data["type"] == "connected"
                assert data["simulation_uid"] == uid

    def test_websocket_invalid_simulation(self, app):
        """Test WebSocket rejects invalid simulation UID."""
        with TestClient(app) as tc:
            with pytest.raises(Exception):
                with tc.websocket_connect("/api/ws/simulations/bad-uid") as ws:
                    ws.receive_json()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_api_websocket.py -v
```

Expected: Failure (no WS endpoint)

- [ ] **Step 3: Implement WebSocket handler**

`backend/src/tsunami/api/websocket.py`:
```python
"""WebSocket handler for real-time simulation updates."""

import asyncio
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tsunami.config import get_settings
from tsunami.database import Base
from tsunami.models import Simulation

router = APIRouter()

# In-memory registry of active connections per simulation
_connections: dict[str, list[WebSocket]] = defaultdict(list)


async def broadcast(sim_uid: str, message: dict):
    """Send a message to all WebSocket clients watching a simulation."""
    for ws in _connections.get(sim_uid, []):
        try:
            await ws.send_json(message)
        except Exception:
            pass  # Client disconnected


@router.websocket("/ws/simulations/{uid}")
async def simulation_ws(websocket: WebSocket, uid: str):
    # Verify simulation exists (sync query — WS setup is lightweight)
    url = get_settings().database_url.replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(url)
    with Session(engine) as session:
        result = session.execute(select(Simulation).where(Simulation.uid == uid))
        sim = result.scalar_one_or_none()
    engine.dispose()

    if sim is None:
        await websocket.close(code=4004, reason="Simulation not found")
        return

    await websocket.accept()
    _connections[uid].append(websocket)

    try:
        await websocket.send_json({"type": "connected", "simulation_uid": uid})
        # Keep connection alive, listen for client messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                break
    finally:
        _connections[uid].remove(websocket)
```

- [ ] **Step 4: Register WebSocket route in app.py**

Update `backend/src/tsunami/app.py` — add after the existing router includes:

```python
    from tsunami.api import websocket as ws_module
    app.include_router(ws_module.router, prefix="/api")
```

The full `create_app` function should now include:
```python
    from tsunami.api import simulations, focus_zones, run, export, bathymetry_routes, presets
    app.include_router(simulations.router, prefix="/api")
    app.include_router(focus_zones.router, prefix="/api")
    app.include_router(run.router, prefix="/api")
    app.include_router(export.router, prefix="/api")
    app.include_router(bathymetry_routes.router, prefix="/api")
    app.include_router(presets.router, prefix="/api")

    from tsunami.api import websocket as ws_module
    app.include_router(ws_module.router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_api_websocket.py -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/src/tsunami/api/websocket.py backend/src/tsunami/app.py backend/tests/test_api_websocket.py
git commit -m "feat: add WebSocket handler for real-time simulation updates"
```

---

### Task 12: Full Test Suite Verification

**Files:**
- No new files — verification only

- [ ] **Step 1: Run the complete test suite**

```bash
cd backend && pytest tests/ -v
```

Expected: All tests pass (44 existing + new API tests)

- [ ] **Step 2: Test the server starts**

```bash
cd backend && timeout 5 python -c "
from tsunami.app import create_app
app = create_app()
print('App created successfully')
print('Routes:')
for route in app.routes:
    if hasattr(route, 'path'):
        methods = getattr(route, 'methods', {'WS'})
        print(f'  {methods} {route.path}')
" || true
```

Expected: App creates without errors, routes are listed

- [ ] **Step 3: Commit any fixes needed**

If any tests fail, fix them and commit.

- [ ] **Step 4: Final commit with all tasks complete**

```bash
git log --oneline -10
```

Verify all Plan 2 commits are in place.
