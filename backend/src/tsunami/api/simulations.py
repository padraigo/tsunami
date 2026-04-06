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
