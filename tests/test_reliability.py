import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import server.main as server
from server.models import Command, MonitorEvent
from server.state import StateManager


def event(**kwargs):
    return MonitorEvent(session_id="s1", tab_name="api", event_type="ready", **kwargs)


def test_snapshot_survives_restart_but_is_unavailable(tmp_path):
    path = tmp_path / "state.json"
    state = StateManager(path)
    state.process_event(event(tail_output="Done", full_output="History"))
    restored = StateManager(path)
    assert restored.sessions["s1"].tail_output == "Done"
    assert not restored.sessions["s1"].available
    assert restored.get_full_output("s1") == "History"
    assert restored.queue[0].status == "pending"
    assert path.stat().st_mode & 0o077 == 0


def test_receipt_time_is_fresh_even_if_monitor_clock_is_wrong():
    state = StateManager()
    state.process_event(event(timestamp=12))
    assert abs(state.sessions["s1"].last_seen - time.time()) < 2


def test_reconcile_removes_closed_session_from_live_targets():
    state = StateManager()
    state.process_event(event())
    assert state.sessions["s1"].available
    state.reconcile([])
    assert not state.sessions["s1"].available
    assert state.queue[0].status == "pending"


def test_corrupt_state_is_preserved_and_reported(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not json")
    with pytest.raises(ValueError, match="snapshot"):
        StateManager(path)
    assert path.read_text() == "not json"


@pytest.mark.parametrize("text", ["", "\nrm -rf /", "hello\r", "\x1b[A", "x" * 4001])
def test_text_payload_rejects_terminal_controls(text):
    with pytest.raises(ValidationError):
        Command(command="send_text", session_id="s1", payload={"text": text})


def test_rename_command_is_validated():
    assert Command(command="rename_tab", session_id="s1", payload={"name": "API"})
    with pytest.raises(ValidationError):
        Command(command="rename_tab", session_id="s1", payload={"name": "\x1b[31m"})


def test_disconnected_reply_does_not_resolve_attention(monkeypatch):
    state = StateManager()
    state.process_event(event())
    monkeypatch.setattr(server, "state", state)
    monkeypatch.setattr(server, "monitor_ws", None)
    with TestClient(server.app) as client:
        response = client.post("/api/sessions/s1/respond", json={"text": "test", "expected_revision": 1})
    assert response.status_code == 503
    assert state.queue[0].status == "pending"


def test_cross_origin_websocket_is_rejected():
    from starlette.websockets import WebSocketDisconnect
    with TestClient(server.app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/dashboard", headers={"origin": "https://untrusted.example"}):
                pass


def test_delivery_waits_for_monitor_ack(monkeypatch):
    state = StateManager()
    state.process_event(event())
    monkeypatch.setattr(server, "state", state)
    class Monitor:
        async def send_json(self, payload):
            assert state.queue[0].status == "pending"
            server.pending_commands[payload["command_id"]].set_result({"ok": True})
    monkeypatch.setattr(server, "monitor_ws", Monitor())
    result = asyncio.run(server.deliver_command(Command(command="send_text", session_id="s1", payload={"text": "test"}, expected_revision=1)))
    assert result["ok"]
    assert state.queue[0].status == "resolved"


def test_timeout_is_uncertain_and_keeps_attention(monkeypatch):
    state = StateManager()
    state.process_event(event())
    monkeypatch.setattr(server, "state", state)
    monkeypatch.setattr(server, "COMMAND_TIMEOUT", 0.01)
    class Monitor:
        async def send_json(self, payload):
            pass
    monkeypatch.setattr(server, "monitor_ws", Monitor())
    result = asyncio.run(server.deliver_command(Command(command="send_text", session_id="s1", payload={"text": "test"}, expected_revision=1)))
    assert not result["ok"] and "unknown" in result["error"].lower()
    assert state.queue[0].status == "pending"
    assert not server.pending_commands


def test_stale_revision_cannot_send(monkeypatch):
    state = StateManager()
    state.process_event(event())
    state.process_event(event(tail_output="new output"))
    monkeypatch.setattr(server, "state", state)
    monkeypatch.setattr(server, "monitor_ws", object())
    result = asyncio.run(server.deliver_command(Command(command="send_text", session_id="s1", payload={"text": "test"}, expected_revision=1)))
    assert not result["ok"]
    assert "changed" in result["error"].lower()

def test_event_between_send_and_ack_does_not_leave_replyable_revision(monkeypatch):
    state = StateManager()
    state.process_event(event())
    monkeypatch.setattr(server, "state", state)
    class Monitor:
        async def send_json(self, payload):
            state.process_event(event(tail_output="new observation"))
            server.pending_commands[payload["command_id"]].set_result({"ok": True})
    monkeypatch.setattr(server, "monitor_ws", Monitor())
    result = asyncio.run(server.deliver_command(Command(command="send_text", session_id="s1", payload={"text": "test"}, expected_revision=1)))
    assert result["ok"]
    assert state.sessions["s1"].status == "working"
    assert state.sessions["s1"].revision == 3
