import asyncio

import pytest

import server.main as server
from server.models import Command, MonitorEvent
from server.state import STALE_AFTER, StateManager


@pytest.mark.parametrize("target", ["stale", "fresh"])
def test_command_expiry_updates_connected_dashboards(monkeypatch, target):
    state = StateManager()
    for sid in ("stale", "fresh"):
        state.process_event(MonitorEvent(
            session_id=sid, tab_name=sid, event_type="ready",
            tail_output="Captured output",
        ))
    state.sessions["stale"].last_seen -= STALE_AFTER + 1
    monkeypatch.setattr(server, "state", state)
    snapshots, sent = [], []

    class Dashboard:
        async def send_json(self, message):
            snapshots.append(message)

    class Monitor:
        async def send_json(self, message):
            sent.append(message)
            server.pending_commands[message["command_id"]].set_result({"ok": True})

    monkeypatch.setattr(server, "dashboard_clients", [Dashboard()])
    monkeypatch.setattr(server, "monitor_ws", Monitor())
    result = asyncio.run(server.deliver_command(Command(
        command="focus_tab", session_id=target,
    )))

    assert result["ok"] is (target == "fresh")
    assert len(sent) == (1 if target == "fresh" else 0)
    assert len(snapshots) == 1
    assert snapshots[0]["type"] == "snapshot"
    assert snapshots[0]["sessions"]["stale"]["available"] is False
    assert snapshots[0]["sessions"]["stale"]["tail_output"] == "Captured output"
    assert snapshots[0]["sessions"]["fresh"]["available"] is True
    # The timer cannot repair a missed broadcast once the state is expired.
    assert state.expire() is False
    assert not server.pending_commands and not server.busy_sessions


@pytest.mark.parametrize("change", ["revision", "disconnect"])
def test_delivery_rechecks_state_after_expiry_broadcast(monkeypatch, change):
    state = StateManager()
    for sid in ("stale", "target"):
        state.process_event(MonitorEvent(
            session_id=sid, tab_name=sid, event_type="ready",
        ))
    state.sessions["stale"].last_seen -= STALE_AFTER + 1
    monkeypatch.setattr(server, "state", state)
    sent = []

    class Dashboard:
        async def send_json(self, message):
            # A monitor update/disconnect may occur while a dashboard send yields.
            if change == "revision":
                state.process_event(MonitorEvent(
                    session_id="target", tab_name="target", event_type="ready",
                    tail_output="New observation",
                ))
            else:
                server.monitor_ws = None

    class Monitor:
        async def send_json(self, message):
            sent.append(message)

    monkeypatch.setattr(server, "dashboard_clients", [Dashboard()])
    monkeypatch.setattr(server, "monitor_ws", Monitor())
    result = asyncio.run(server.deliver_command(Command(
        command="send_text", session_id="target", expected_revision=1,
        payload={"text": "Follow up"},
    )))
    assert not result["ok"]
    assert result["code"] == (409 if change == "revision" else 503)
    assert ("changed" if change == "revision" else "disconnected") in result["error"]
    assert not sent
    assert not server.pending_commands and not server.busy_sessions
