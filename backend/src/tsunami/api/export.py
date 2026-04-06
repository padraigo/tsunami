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
