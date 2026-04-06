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
