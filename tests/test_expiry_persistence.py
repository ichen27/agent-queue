"""Storage failures must not stop freshness checks or hide expired sessions."""
import asyncio
import json
from types import SimpleNamespace

import pytest

import server.main as server
import server.state as state_module
from server.models import MonitorEvent
from server.state import StateManager


@pytest.mark.parametrize("failed_saves", [0, 1, 2], ids=["healthy", "transient", "persistent"])
def test_expiry_continues_and_broadcasts_when_saving_fails(monkeypatch, tmp_path, caplog, failed_saves):
    now = 100
    monkeypatch.setattr(state_module, "time", SimpleNamespace(time=lambda: now))
    state = StateManager(tmp_path / "state.json")
    for sid in ("first", "later"):
        state.process_event(MonitorEvent(
            session_id=sid, tab_name=sid, event_type="ready", tail_output="Captured",
        ))
    state.sessions["first"].last_seen = 0
    state.save()
    original_snapshot = state.path.read_bytes()
    original_save = state.save
    writes = 0

    def save():
        nonlocal writes
        writes += 1
        if writes <= failed_saves:
            raise OSError("Synthetic storage failure")
        original_save()

    monkeypatch.setattr(state, "save", save)
    monkeypatch.setattr(server, "state", state)
    monkeypatch.setattr(server, "monitor_ws", None)
    snapshots = []

    class Dashboard:
        async def send_json(self, message):
            snapshots.append(message)

    monkeypatch.setattr(server, "dashboard_clients", [Dashboard()])
    ticks = iter([100, 110, 120])

    async def tick(delay):
        nonlocal now
        assert delay == 3
        try:
            now = next(ticks)
        except StopIteration:
            raise asyncio.CancelledError
        await asyncio.sleep(0)

    # Substitute the module binding, leaving the test runner's asyncio untouched.
    monkeypatch.setattr(server, "asyncio", SimpleNamespace(sleep=tick))

    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await server.expire_sessions()

    asyncio.run(scenario())
    assert writes == 2
    assert len(snapshots) == 2  # No redundant update while nothing expires at 110.
    assert snapshots[0]["sessions"]["first"]["available"] is False
    assert snapshots[0]["sessions"]["later"]["available"] is True
    assert all(not session["available"] for session in snapshots[1]["sessions"].values())
    assert all(session["tail_output"] == "Captured" for session in snapshots[1]["sessions"].values())
    errors = [record for record in caplog.records if record.name == "server.main"]
    assert len(errors) == failed_saves
    assert all(record.getMessage() == "Could not persist expired sessions" for record in errors)
    if failed_saves == 2:
        assert state.path.read_bytes() == original_snapshot
    else:
        saved = json.loads(state.path.read_text())
        assert all(not session["available"] for session in saved["sessions"].values())
