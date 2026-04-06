"""Frame data endpoint for wave animation playback."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tsunami.api.deps import get_db
from tsunami.models import Simulation

router = APIRouter(tags=["frames"])


@router.get("/simulations/{uid}/frames")
async def get_frames(uid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Simulation).where(Simulation.uid == uid))
    sim = result.scalar_one_or_none()
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")

    if not sim.coarse_result_path:
        raise HTTPException(status_code=404, detail="No results available — run simulation first")

    frames_path = Path(sim.coarse_result_path) / "frames.json"
    if not frames_path.exists():
        raise HTTPException(status_code=404, detail="No frame data available")

    with open(frames_path) as f:
        data = json.load(f)

    return JSONResponse(content=data)
