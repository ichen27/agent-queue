"""A wall-clock rollback cannot establish that a captured terminal is still fresh."""
import asyncio
import json

import pytest

import server.main as server
import server.state as state_module
from server.models import Command, MonitorEvent
from server.state import STALE_AFTER, StateManager


@pytest.mark.parametrize("elapsed,expired", [
    (-1, True), (0, False), (STALE_AFTER, False), (STALE_AFTER + 1, True),
])
def test_expiry_handles_backward_clock_and_retains_forward_boundary(monkeypatch, elapsed, expired):
    monkeypatch.setattr(state_module.time, "time", lambda: 1000)
    state = StateManager()
    state.process_event(MonitorEvent(session_id="s", tab_name="Example", event_type="ready"))
    monkeypatch.setattr(state_module.time, "time", lambda: 1000 + elapsed)
    assert state.expire() is expired
    assert state.sessions["s"].available is not expired
    assert state.queue[0].status == "pending"
    assert state.expire() is False


def test_clock_rollback_blocks_delivery_until_new_observation(monkeypatch, tmp_path):
    monkeypatch.setattr(state_module.time, "time", lambda: 1000)
    state = StateManager(tmp_path / "state.json")
    event = MonitorEvent(
        session_id="s", tab_name="Example", event_type="ready", full_output="Captured history",
    )
    state.process_event(event)
    monkeypatch.setattr(server, "state", state)
    monkeypatch.setattr(server, "pending_commands", {})
    monkeypatch.setattr(server, "busy_sessions", set())
    sent, snapshots = [], []

    class Dashboard:
        async def send_json(self, message):
            snapshots.append(message)

    class Monitor:
        async def send_json(self, message):
            sent.append(message)
            server.pending_commands[message["command_id"]].set_result({"ok": True})

    monkeypatch.setattr(server, "dashboard_clients", [Dashboard()])
    monkeypatch.setattr(server, "monitor_ws", Monitor())
    monkeypatch.setattr(state_module.time, "time", lambda: 900)

    async def scenario():
        command = Command(
            command="send_text", session_id="s", expected_revision=1,
            payload={"text": "Continue"},
        )
        rejected = await server.deliver_command(command)
        assert rejected["ok"] is False and rejected["code"] == 409
        assert not sent
        assert len(snapshots) == 1
        assert snapshots[0]["sessions"]["s"]["available"] is False
        assert state.queue[0].status == "pending"
        assert json.loads(state.path.read_text())["sessions"]["s"]["available"] is False
        restored = StateManager(state.path)
        assert not restored.sessions["s"].available
        assert restored.get_full_output("s") == "Captured history"

        # An inventory cannot restore delivery authority.
        state.reconcile(["s"])
        assert not state.sessions["s"].available
        state.process_event(event)
        assert state.sessions["s"].available
        stale_revision = await server.deliver_command(command)
        assert stale_revision["ok"] is False and not sent

        fresh = await server.deliver_command(Command(
            command="send_text", session_id="s", expected_revision=2,
            payload={"text": "Continue"},
        ))
        assert fresh["ok"] is True
        assert len(sent) == 1
        assert state.queue[0].status == "resolved"
        assert not server.pending_commands and not server.busy_sessions

    asyncio.run(scenario())
