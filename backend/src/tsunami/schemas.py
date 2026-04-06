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
