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
