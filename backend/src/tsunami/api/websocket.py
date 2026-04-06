"""WebSocket handler for real-time simulation updates."""

import asyncio
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tsunami.config import get_settings
from tsunami.models import Simulation

router = APIRouter()

# In-memory registry of active connections per simulation
_connections: dict[str, list[WebSocket]] = defaultdict(list)


async def broadcast(sim_uid: str, message: dict):
    """Send a message to all WebSocket clients watching a simulation."""
    for ws in _connections.get(sim_uid, []):
        try:
            await ws.send_json(message)
        except Exception:
            pass  # Client disconnected


@router.websocket("/ws/simulations/{uid}")
async def simulation_ws(websocket: WebSocket, uid: str):
    # Verify simulation exists (sync query — WS setup is lightweight)
    url = get_settings().database_url.replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(url)
    with Session(engine) as session:
        result = session.execute(select(Simulation).where(Simulation.uid == uid))
        sim = result.scalar_one_or_none()
    engine.dispose()

    if sim is None:
        await websocket.close(code=4004, reason="Simulation not found")
        return

    await websocket.accept()
    _connections[uid].append(websocket)

    try:
        await websocket.send_json({"type": "connected", "simulation_uid": uid})
        # Keep connection alive, listen for client messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                break
    finally:
        _connections[uid].remove(websocket)
