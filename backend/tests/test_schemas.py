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
