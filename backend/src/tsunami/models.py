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
