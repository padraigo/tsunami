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
