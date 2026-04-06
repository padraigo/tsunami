import pytest


@pytest.fixture
async def sim_uid(client):
    resp = await client.post("/api/simulations", json={
        "name": "Run Test",
        "earthquake_lat": 0.0, "earthquake_lon": 100.0,
        "earthquake_magnitude": 7.5, "earthquake_direction": 270.0,
        "grid_resolution_km": 50.0,  # coarse for speed
        "duration_hours": 0.5,  # 30 minutes
    })
    return resp.json()["uid"]


class TestRunCoarse:
    @pytest.mark.anyio
    async def test_run_coarse_starts_and_completes(self, client, sim_uid):
        resp = await client.post(f"/api/simulations/{sim_uid}/run-coarse")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "coarse_complete"
        assert "impacts" in data

    @pytest.mark.anyio
    async def test_run_coarse_updates_simulation_status(self, client, sim_uid):
        await client.post(f"/api/simulations/{sim_uid}/run-coarse")
        resp = await client.get(f"/api/simulations/{sim_uid}")
        assert resp.json()["status"] == "coarse_complete"

    @pytest.mark.anyio
    async def test_run_coarse_nonexistent_sim(self, client):
        resp = await client.post("/api/simulations/bad-uid/run-coarse")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_get_coarse_result(self, client, sim_uid):
        await client.post(f"/api/simulations/{sim_uid}/run-coarse")
        resp = await client.get(f"/api/simulations/{sim_uid}/coarse-result")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "coarse_complete"
