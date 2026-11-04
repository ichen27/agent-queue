"""A failed save must not replace recoverable history or leave partial captures."""
import pytest

import server.state as state_module
from server.models import MonitorEvent
from server.state import StateManager


@pytest.mark.parametrize("existing_snapshot", [False, True])
@pytest.mark.parametrize("failure_stage", ["partial_write", "fsync", "replace"])
def test_failed_save_preserves_snapshot_and_can_retry(
    tmp_path, monkeypatch, existing_snapshot, failure_stage
):
    path = tmp_path / "state.json"
    state = StateManager()
    state.process_event(MonitorEvent(
        session_id="session", tab_name="Example", event_type="ready",
        tail_output="Previous excerpt", full_output="Previous history",
    ))
    state.path = path
    if existing_snapshot:
        state.save()
    previous_bytes = path.read_bytes() if existing_snapshot else None
    previous_state = StateManager(path) if existing_snapshot else None

    # Change all persisted collections without saving the new observation yet.
    state.path = None
    state.process_event(MonitorEvent(
        session_id="session", tab_name="Example", event_type="working",
        tail_output="New excerpt", full_output="New history",
    ))
    state.path = path
    error = OSError("Injected storage failure")

    def fail(*args, **kwargs):
        if failure_stage == "partial_write":
            args[1].write('{"version": 1, "sessions":')
        raise error

    with monkeypatch.context() as patch:
        if failure_stage == "partial_write":
            patch.setattr(state_module.json, "dump", fail)
        else:
            patch.setattr(state_module.os, failure_stage, fail)
        with pytest.raises(OSError) as caught:
            state.save()
        assert caught.value is error

    if existing_snapshot:
        assert path.read_bytes() == previous_bytes
        restored = StateManager(path)
        assert restored.get_snapshot() == previous_state.get_snapshot()
        assert restored.full_outputs == previous_state.full_outputs
        assert restored.queue[0].status == "pending"
        assert not restored.sessions["session"].available
    else:
        assert not path.exists()
    assert list(tmp_path.glob(".snapshot-*")) == []

    # Removing the fault permits the same in-memory state to be saved intact.
    state.save()
    restored = StateManager(path)
    expected = state.get_snapshot()
    expected["sessions"]["session"]["available"] = False
    assert restored.get_snapshot() == expected
    assert restored.full_outputs == {"session": "New history"}
    assert restored.queue[0].status == "resolved"
    assert path.stat().st_mode & 0o077 == 0
    assert list(tmp_path.glob(".snapshot-*")) == []
