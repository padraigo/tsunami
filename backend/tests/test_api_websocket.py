import pytest
from starlette.testclient import TestClient


class TestWebSocket:
    def test_websocket_connect_and_receive(self, app):
        """Test WebSocket connection and message format."""
        # Use sync TestClient for WebSocket testing
        with TestClient(app) as tc:
            # First create a simulation via REST
            resp = tc.post("/api/simulations", json={
                "name": "WS Test",
                "earthquake_lat": 0.0, "earthquake_lon": 100.0,
                "earthquake_magnitude": 7.0, "earthquake_direction": 0.0,
            })
            uid = resp.json()["uid"]

            with tc.websocket_connect(f"/api/ws/simulations/{uid}") as ws:
                data = ws.receive_json()
                assert data["type"] == "connected"
                assert data["simulation_uid"] == uid

    def test_websocket_invalid_simulation(self, app):
        """Test WebSocket rejects invalid simulation UID."""
        with TestClient(app) as tc:
            with pytest.raises(Exception):
                with tc.websocket_connect("/api/ws/simulations/bad-uid") as ws:
                    ws.receive_json()
