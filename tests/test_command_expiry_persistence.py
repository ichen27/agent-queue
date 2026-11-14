"""Command freshness checks survive storage failure on both public transports."""
from fastapi.testclient import TestClient
import pytest

import server.main as server
from server.models import MonitorEvent
from server.state import STALE_AFTER, StateManager


@pytest.mark.parametrize("transport", ["http", "websocket"])
@pytest.mark.parametrize("target", ["stale", "fresh"])
def test_command_expiry_storage_failure_keeps_delivery_safe(
    monkeypatch, tmp_path, caplog, transport, target,
):
    state = StateManager(tmp_path / "state.json")
    for sid in ("stale", "fresh"):
        state.process_event(MonitorEvent(
            session_id=sid, tab_name=sid, event_type="ready",
            tail_output="Captured output",
        ))
    state.sessions["stale"].last_seen -= STALE_AFTER + 1
    monkeypatch.setattr(server, "state", state)
    monkeypatch.setattr(server, "dashboard_clients", [])
    monkeypatch.setattr(server, "pending_commands", {})
    monkeypatch.setattr(server, "busy_sessions", set())
    original_save = state.save
    failed = False

    def save():
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("Synthetic snapshot failure")
        original_save()

    monkeypatch.setattr(state, "save", save)
    sent = []

    class Monitor:
        async def send_json(self, message):
            sent.append(message)
            server.pending_commands[message["command_id"]].set_result({"ok": True})

    monkeypatch.setattr(server, "monitor_ws", Monitor())
    # No lifespan timer: expiry must be triggered by this request.
    client = TestClient(server.app)
    if transport == "http":
        response = client.post(f"/api/sessions/{target}/respond", json={
            "text": "Continue", "expected_revision": 1,
        })
        assert response.status_code == (409 if target == "stale" else 200)
        result = response.json()
        assert client.get("/api/sessions").json()["sessions"]["stale"]["available"] is False
    else:
        with client.websocket_connect("/ws/dashboard") as ws:
            assert ws.receive_json()["type"] == "snapshot"
            ws.send_json({
                "command": "send_text", "command_id": "first", "session_id": target,
                "payload": {"text": "Continue"}, "expected_revision": 1,
            })
            expired = ws.receive_json()
            assert expired["type"] == "snapshot"
            assert expired["sessions"]["stale"]["available"] is False
            assert expired["sessions"]["stale"]["tail_output"] == "Captured output"
            result = ws.receive_json()
            if target == "fresh":
                assert result["type"] == "snapshot"  # Acknowledged text update.
                result = ws.receive_json()
            assert result["type"] == "command_result"
            assert result["command_id"] == "first"
            # The same connection remains usable; no reconnect or automatic replay.
            ws.send_json({"command": "focus_tab", "command_id": "second", "session_id": "fresh"})
            followup = ws.receive_json()
            assert followup["command_id"] == "second" and followup["ok"]
        assert not server.dashboard_clients

    assert failed
    assert result["ok"] is (target == "fresh")
    if target == "stale":
        assert "unavailable" in result["error"]
    expected = (1 if target == "fresh" else 0) + (1 if transport == "websocket" else 0)
    assert len(sent) == expected
    assert all(message["session_id"] == "fresh" for message in sent)
    assert not server.pending_commands and not server.busy_sessions
    assert not state.sessions["stale"].available
    assert state.sessions["stale"].tail_output == "Captured output"
    assert sum(record.getMessage() == "Could not persist expired sessions" for record in caplog.records) == 1
