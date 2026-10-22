import json
import pytest
import server.state as state_module
from server.models import MonitorEvent
from server.state import StateManager

@pytest.mark.parametrize("data", [
    [], None, {}, {"version": 2, "sessions": {}, "queue": []},
    {"version": True, "sessions": {}, "queue": []},
    {"version": 1, "sessions": [], "queue": []},
    {"version": 1, "sessions": {}, "queue": {}},
    {"version": 1, "sessions": {"s": None}, "queue": []},
    {"version": 1, "sessions": {}, "queue": [None]},
    {"version": 1, "sessions": {}, "queue": [], "full_outputs": []},
    {"version": 1, "sessions": {}, "queue": [], "full_outputs": {"s": 42}},
    {"version": 1, "sessions": {"wrong": {"session_id": "s", "tab_name": "tab"}}, "queue": []},
])
def test_invalid_snapshot_schema_is_preserved_with_recovery_message(tmp_path, data):
    path = tmp_path / "state.json"
    original = json.dumps(data)
    path.write_text(original)
    with pytest.raises(ValueError, match="preserve or move"):
        StateManager(path)
    assert path.read_text() == original

def test_restore_enforces_limits_and_removes_orphan_output(tmp_path, monkeypatch):
    source = StateManager()
    for i in range(5):
        source.process_event(MonitorEvent(session_id=f"s{i}", tab_name="tab", event_type="ready", full_output=f"output {i}"))
        source.sessions[f"s{i}"].last_seen = i
    data = {"version": 1, **source.get_snapshot(), "full_outputs": {**source.full_outputs, "orphan": "old"}}
    path = tmp_path / "state.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(state_module, "MAX_SESSIONS", 3)
    monkeypatch.setattr(state_module, "MAX_QUEUE_ITEMS", 2)
    restored = StateManager(path)
    assert set(restored.sessions) == {"s2", "s3", "s4"}
    assert [q.session_id for q in restored.queue] == ["s3", "s4"]
    assert restored.full_outputs == {f"s{i}": f"output {i}" for i in range(2, 5)}
    assert all(not s.available for s in restored.sessions.values())
    assert json.loads(path.read_text()) == data


def test_restore_without_optional_outputs_preserves_history(tmp_path):
    source = StateManager()
    source.process_event(MonitorEvent(session_id="s", tab_name="tab", event_type="ready"))
    data = {"version": 1, **source.get_snapshot()}
    path = tmp_path / "state.json"
    original = json.dumps(data)
    path.write_text(original)
    restored = StateManager(path)
    assert restored.queue[0].model_dump() == data["queue"][0]
    assert restored.sessions["s"].revision == source.sessions["s"].revision
    assert not restored.sessions["s"].available
    assert restored.get_full_output("s") == ""
    assert path.read_text() == original


def test_restore_removes_orphans_even_below_limits(tmp_path):
    source = StateManager()
    source.process_event(MonitorEvent(session_id="missing", tab_name="tab", event_type="ready"))
    source.process_event(MonitorEvent(session_id="kept", tab_name="tab", event_type="ready", full_output="History"))
    data = {"version": 1, **source.get_snapshot(), "full_outputs": source.full_outputs}
    del data["sessions"]["missing"]
    path = tmp_path / "state.json"
    original = json.dumps(data)
    path.write_text(original)
    restored = StateManager(path)
    assert [q.session_id for q in restored.queue] == ["kept"]
    assert restored.full_outputs == {"kept": "History"}
    assert path.read_text() == original
    restored.save()
    again = StateManager(path)
    assert again.get_snapshot() == restored.get_snapshot()
    assert again.full_outputs == restored.full_outputs
