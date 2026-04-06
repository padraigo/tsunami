import pytest


class TestCreateSimulation:
    @pytest.mark.anyio
    async def test_create_simulation(self, client):
        resp = await client.post("/api/simulations", json={
            "name": "Tohoku 2011",
            "earthquake_lat": 38.3,
            "earthquake_lon": 142.4,
            "earthquake_magnitude": 9.1,
            "earthquake_direction": 290.0,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Tohoku 2011"
        assert data["status"] == "pending"
        assert "uid" in data

    @pytest.mark.anyio
    async def test_create_simulation_validation_error(self, client):
        resp = await client.post("/api/simulations", json={
            "name": "Bad",
            "earthquake_lat": 0.0,
            "earthquake_lon": 0.0,
            "earthquake_magnitude": 20.0,  # invalid
            "earthquake_direction": 0.0,
        })
        assert resp.status_code == 422


class TestListSimulations:
    @pytest.mark.anyio
    async def test_list_empty(self, client):
        resp = await client.get("/api/simulations")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.anyio
    async def test_list_after_create(self, client):
        await client.post("/api/simulations", json={
            "name": "Sim 1",
            "earthquake_lat": 0.0, "earthquake_lon": 100.0,
            "earthquake_magnitude": 8.0, "earthquake_direction": 270.0,
        })
        resp = await client.get("/api/simulations")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestGetSimulation:
    @pytest.mark.anyio
    async def test_get_by_uid(self, client):
        create_resp = await client.post("/api/simulations", json={
            "name": "Get Test",
            "earthquake_lat": 0.0, "earthquake_lon": 100.0,
            "earthquake_magnitude": 7.5, "earthquake_direction": 0.0,
        })
        uid = create_resp.json()["uid"]
        resp = await client.get(f"/api/simulations/{uid}")
        assert resp.status_code == 200
        assert resp.json()["uid"] == uid

    @pytest.mark.anyio
    async def test_get_not_found(self, client):
        resp = await client.get("/api/simulations/nonexistent")
        assert resp.status_code == 404


class TestDeleteSimulation:
    @pytest.mark.anyio
    async def test_delete(self, client):
        create_resp = await client.post("/api/simulations", json={
            "name": "Delete Me",
            "earthquake_lat": 0.0, "earthquake_lon": 100.0,
            "earthquake_magnitude": 7.0, "earthquake_direction": 0.0,
        })
        uid = create_resp.json()["uid"]
        resp = await client.delete(f"/api/simulations/{uid}")
        assert resp.status_code == 204
        get_resp = await client.get(f"/api/simulations/{uid}")
        assert get_resp.status_code == 404
