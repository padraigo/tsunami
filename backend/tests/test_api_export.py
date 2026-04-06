import pytest


class TestPresets:
    @pytest.mark.anyio
    async def test_list_preset_locations(self, client):
        resp = await client.get("/api/presets/locations")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "name" in data[0]
        assert "lat" in data[0]
        assert "lon" in data[0]


class TestBathymetryCheck:
    @pytest.mark.anyio
    async def test_check_availability(self, client):
        resp = await client.get(
            "/api/bathymetry/check",
            params={"lat_min": -2, "lat_max": 2, "lon_min": 98, "lon_max": 102},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["procedural"] is True


class TestExport:
    @pytest.mark.anyio
    async def test_export_nonexistent_sim(self, client):
        resp = await client.get("/api/simulations/bad-uid/export", params={"format": "geojson"})
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_export_before_run(self, client):
        create_resp = await client.post("/api/simulations", json={
            "name": "Export Test",
            "earthquake_lat": 0.0, "earthquake_lon": 100.0,
            "earthquake_magnitude": 7.0, "earthquake_direction": 0.0,
        })
        uid = create_resp.json()["uid"]
        resp = await client.get(f"/api/simulations/{uid}/export", params={"format": "geojson"})
        assert resp.status_code == 400  # no results yet
