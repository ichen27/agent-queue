import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import json
import socket
import threading
import time
import pytest
import uvicorn
import websockets
import httpx
from fastapi.testclient import TestClient
import server.main as main_module
from server.main import app, state

_SERVER_HOST = "127.0.0.1"
_SERVER_PORT = 18766
_BASE_WS = f"ws://{_SERVER_HOST}:{_SERVER_PORT}"
_BASE_HTTP = f"http://{_SERVER_HOST}:{_SERVER_PORT}"


@pytest.fixture(scope="module")
def live_server():
    config = uvicorn.Config(app, host=_SERVER_HOST, port=_SERVER_PORT, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            s = socket.create_connection((_SERVER_HOST, _SERVER_PORT), timeout=0.1)
            s.close()
            break
        except (ConnectionRefusedError, OSError):
            time.sleep(0.1)
    yield
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def reset_state():
    state.sessions.clear()
    state.queue.clear()
    state.full_outputs.clear()
    main_module.monitor_ws = None
    main_module.dashboard_clients.clear()
    yield


def test_get_sessions_empty():
    client = TestClient(app)
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sessions"] == {}
    assert data["queue"] == []

def test_respond_to_session_no_session():
    client = TestClient(app)
    resp = client.post("/api/sessions/nonexistent/respond", json={"text": "hello"})
    assert resp.status_code == 404

def test_dashboard_websocket_receives_snapshot():
    client = TestClient(app)
    with client.websocket_connect("/ws/dashboard") as ws:
        data = ws.receive_json()
        assert data["type"] == "snapshot"
        assert "sessions" in data
        assert "queue" in data

def test_monitor_websocket_processes_event(live_server):
    """
    Tests that monitor events are forwarded to dashboard clients.
    Uses a live server so both WebSocket connections share the same event loop.
    """
    async def _test():
        async with websockets.connect(f"{_BASE_WS}/ws/dashboard") as dash_ws:
            raw = await asyncio.wait_for(dash_ws.recv(), timeout=5)
            snapshot = json.loads(raw)
            assert snapshot["type"] == "snapshot"

            async with websockets.connect(f"{_BASE_WS}/ws/monitor") as mon_ws:
                await mon_ws.send(json.dumps({
                    "session_id": "s1",
                    "tab_name": "test-tab",
                    "event_type": "ready",
                    "tail_output": "Done!",
                    "full_output": "Full history",
                }))
                raw = await asyncio.wait_for(dash_ws.recv(), timeout=5)
                data = json.loads(raw)
                if data["type"] == "snapshot":
                    data = json.loads(await asyncio.wait_for(dash_ws.recv(), timeout=5))
                assert data["type"] == "event"
                assert data["event"]["session_id"] == "s1"

    asyncio.run(_test())
