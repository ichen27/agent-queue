"""Real WebSocket clients exercise delivery boundaries on one event loop."""
import asyncio
import json
import socket
import threading
import time
import pytest
import uvicorn
import websockets
import httpx
import server.main as server
from server.state import StateManager

BASE = "ws://127.0.0.1:18765"


@pytest.fixture(scope="module", autouse=True)
def live_server():
    config = uvicorn.Config(server.app, host="127.0.0.1", port=18765, log_level="error")
    instance = uvicorn.Server(config)
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", 18765), timeout=.1):
                break
        except OSError:
            time.sleep(.1)
    yield
    instance.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(server, "state", StateManager())
    server.monitor_ws = None
    server.pending_commands.clear()
    server.busy_sessions.clear()
    server.dashboard_clients.clear()


async def receive(ws, kind):
    for _ in range(20):
        message = json.loads(await asyncio.wait_for(ws.recv(), 5))
        if message["type"] == kind:
            return message
    raise AssertionError(f"No {kind} message")


async def publish(mon, status="ready"):
    await mon.send(json.dumps({"session_id": "s1", "tab_name": "api", "event_type": status, "tail_output": "Done", "full_output": "History"}))


def test_full_flow_waits_for_ack_and_restores_snapshot():
    async def scenario():
        async with websockets.connect(BASE + "/ws/dashboard") as dash, websockets.connect(BASE + "/ws/monitor") as mon:
            await publish(mon)
            event = await receive(dash, "event")
            command = {"command": "send_text", "session_id": "s1", "expected_revision": event["session"]["revision"], "payload": {"text": "Add tests"}}
            await dash.send(json.dumps(command))
            sent = json.loads(await asyncio.wait_for(mon.recv(), 5))
            assert sent["payload"]["text"] == "Add tests"
            assert server.state.queue[0].status == "pending"
            await mon.send(json.dumps({"type": "command_ack", "command_id": sent["command_id"], "ok": True}))
            result = await receive(dash, "command_result")
            assert result["ok"]
            assert server.state.queue[0].status == "resolved"
            async with websockets.connect(BASE + "/ws/dashboard") as reconnected:
                snap = await receive(reconnected, "snapshot")
                assert snap["sessions"]["s1"]["status"] == "working"
    asyncio.run(scenario())


def test_permission_decisions_require_the_terminal():
    async def scenario():
        async with websockets.connect(BASE + "/ws/dashboard") as dash, websockets.connect(BASE + "/ws/monitor") as mon:
            await publish(mon, "permission_prompt")
            event = await receive(dash, "event")
            await dash.send(json.dumps({"command": "send_text", "session_id": "s1", "expected_revision": event["session"]["revision"], "payload": {"text": "y"}}))
            result = await receive(dash, "command_result")
            assert not result["ok"]
            assert server.state.queue[0].status == "pending"
    asyncio.run(scenario())


def test_rest_disconnected_response_is_not_success():
    async def scenario():
        async with websockets.connect(BASE + "/ws/monitor") as mon:
            await publish(mon)
            await asyncio.sleep(.05)
        await asyncio.sleep(.05)
    asyncio.run(scenario())
    response = httpx.post("http://127.0.0.1:18765/api/sessions/s1/respond", json={"text": "Add tests", "expected_revision": 1})
    assert response.status_code == 503
    assert server.state.queue[0].status == "pending"


def test_closed_inventory_disables_session_and_reconnect_replays():
    async def scenario():
        async with websockets.connect(BASE + "/ws/dashboard") as dash:
            async with websockets.connect(BASE + "/ws/monitor") as mon:
                await publish(mon)
                await receive(dash, "event")
                await mon.send(json.dumps({"type": "inventory", "session_ids": []}))
                while True:
                    snap = await receive(dash, "snapshot")
                    if "s1" in snap["sessions"] and not snap["sessions"]["s1"]["available"]:
                        break
            await asyncio.sleep(.05)
            async with websockets.connect(BASE + "/ws/monitor") as mon:
                await publish(mon)
                event = await receive(dash, "event")
                assert event["session"]["available"]
    asyncio.run(scenario())


def test_second_monitor_cannot_replace_first():
    async def scenario():
        async with websockets.connect(BASE + "/ws/monitor") as first:
            await publish(first)
            async with websockets.connect(BASE + "/ws/monitor") as second:
                with pytest.raises(websockets.ConnectionClosed):
                    await second.recv()
            assert server.monitor_ws is not None
    asyncio.run(scenario())


def test_malformed_command_does_not_disconnect_dashboard():
    async def scenario():
        async with websockets.connect(BASE + "/ws/dashboard") as dash:
            await receive(dash, "snapshot")
            await dash.send(json.dumps({"command": "unknown"}))
            result = await receive(dash, "command_result")
            assert not result["ok"]
            await dash.send(json.dumps({"command": "focus_tab", "session_id": "missing", "payload": {}}))
            assert (await receive(dash, "command_result"))["code"] == 404
    asyncio.run(scenario())


def test_non_object_monitor_message_is_rejected_without_losing_connection():
    async def scenario():
        async with websockets.connect(BASE + "/ws/monitor") as mon:
            await mon.send("[]")
            assert (await receive(mon, "error"))["error"] == "Invalid monitor message"
            await publish(mon)
            await asyncio.sleep(.05)
            assert server.state.sessions["s1"].available
    asyncio.run(scenario())
