from types import SimpleNamespace

import pytest

import server.state as state_module
from server.models import MonitorEvent
from server.state import StateManager


@pytest.mark.parametrize("restore", [False, True])
@pytest.mark.parametrize("incoming_time", [500, 3000])
def test_incoming_observation_survives_bounded_trimming(tmp_path, monkeypatch, restore, incoming_time):
    monkeypatch.setattr(state_module, "MAX_SESSIONS", 2)
    now = 1000
    monkeypatch.setattr(state_module, "time", SimpleNamespace(time=lambda: now))
    path = tmp_path / "state.json"
    state = StateManager(path)

    def observe(sid):
        return state.process_event(MonitorEvent(
            session_id=sid, tab_name=sid, event_type="ready",
            tail_output=f"Tail {sid}", full_output=f"History {sid}",
        ))

    observe("oldest")
    now = 2000
    observe("newer")
    if restore:
        state = StateManager(path)
    now = incoming_time
    item = observe("incoming")

    # A fresh event must be available for the relay's immediate event broadcast,
    # even if saved timestamps are ahead of the current clock.
    assert set(state.sessions) == {"newer", "incoming"}
    assert state.sessions["incoming"].available
    assert state.sessions["incoming"].last_seen == incoming_time
    assert state.sessions["incoming"].tail_output == "Tail incoming"
    assert item in state.queue
    assert {q.session_id for q in state.queue} == {"newer", "incoming"}
    assert state.full_outputs == {
        "newer": "History newer", "incoming": "History incoming",
    }
    persisted = StateManager(path)
    assert set(persisted.sessions) == set(state.sessions)
    assert persisted.full_outputs == state.full_outputs
    assert all(not session.available for session in persisted.sessions.values())
