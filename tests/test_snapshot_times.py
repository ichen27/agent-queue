import json
import pytest
from server.models import MonitorEvent
from server.state import StateManager


@pytest.mark.parametrize("field", ["last_seen", "last_event_time", "created_at"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_snapshot_times_fail_with_recovery_message(tmp_path, field, value):
    source = StateManager()
    source.process_event(MonitorEvent(session_id="s", tab_name="tab", event_type="ready"))
    data = {"version": 1, **source.get_snapshot()}
    record = data["queue"][0] if field == "created_at" else data["sessions"]["s"]
    record[field] = value
    path = tmp_path / "state.json"
    original = json.dumps(data)
    path.write_text(original)
    with pytest.raises(ValueError, match="preserve or move"):
        StateManager(path)
    assert path.read_text() == original
