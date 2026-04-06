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
