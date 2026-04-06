import pytest


@pytest.fixture
async def sim_uid(client):
    resp = await client.post("/api/simulations", json={
        "name": "Zone Parent",
        "earthquake_lat": 0.0, "earthquake_lon": 100.0,
        "earthquake_magnitude": 8.0, "earthquake_direction": 270.0,
    })
    return resp.json()["uid"]


class TestAddFocusZone:
    @pytest.mark.anyio
    async def test_add_zone(self, client, sim_uid):
        resp = await client.post(f"/api/simulations/{sim_uid}/focus-zones", json={
            "name": "Zone 1",
            "lat_min": -1.0, "lat_max": 1.0,
            "lon_min": 99.0, "lon_max": 101.0,
            "source": "user",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Zone 1"
        assert data["status"] == "pending"

    @pytest.mark.anyio
    async def test_add_zone_to_nonexistent_sim(self, client):
        resp = await client.post("/api/simulations/bad-uid/focus-zones", json={
            "name": "Zone 1",
            "lat_min": -1.0, "lat_max": 1.0,
            "lon_min": 99.0, "lon_max": 101.0,
            "source": "user",
        })
        assert resp.status_code == 404


class TestListFocusZones:
    @pytest.mark.anyio
    async def test_list_zones(self, client, sim_uid):
        await client.post(f"/api/simulations/{sim_uid}/focus-zones", json={
            "name": "Z1", "lat_min": -1.0, "lat_max": 1.0,
            "lon_min": 99.0, "lon_max": 101.0, "source": "user",
        })
        resp = await client.get(f"/api/simulations/{sim_uid}/focus-zones")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestUpdateFocusZone:
    @pytest.mark.anyio
    async def test_update_zone_name(self, client, sim_uid):
        create_resp = await client.post(f"/api/simulations/{sim_uid}/focus-zones", json={
            "name": "Old Name", "lat_min": -1.0, "lat_max": 1.0,
            "lon_min": 99.0, "lon_max": 101.0, "source": "user",
        })
        zone_uid = create_resp.json()["uid"]
        resp = await client.put(
            f"/api/simulations/{sim_uid}/focus-zones/{zone_uid}",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"


class TestDeleteFocusZone:
    @pytest.mark.anyio
    async def test_delete_zone(self, client, sim_uid):
        create_resp = await client.post(f"/api/simulations/{sim_uid}/focus-zones", json={
            "name": "Bye", "lat_min": -1.0, "lat_max": 1.0,
            "lon_min": 99.0, "lon_max": 101.0, "source": "user",
        })
        zone_uid = create_resp.json()["uid"]
        resp = await client.delete(f"/api/simulations/{sim_uid}/focus-zones/{zone_uid}")
        assert resp.status_code == 204
        list_resp = await client.get(f"/api/simulations/{sim_uid}/focus-zones")
        assert len(list_resp.json()) == 0
