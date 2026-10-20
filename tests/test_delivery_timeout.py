import asyncio
import server.main as server
from server.models import Command, MonitorEvent
from server.state import StateManager

def test_timeout_also_bounds_a_stalled_monitor_send(monkeypatch):
    state = StateManager()
    state.process_event(MonitorEvent(session_id="s", tab_name="tab", event_type="ready"))
    monkeypatch.setattr(server, "state", state)
    monkeypatch.setattr(server, "COMMAND_TIMEOUT", 0.01)
    sends = []
    class Monitor:
        async def send_json(self, payload):
            sends.append(payload)
            await asyncio.Event().wait()
    monkeypatch.setattr(server, "monitor_ws", Monitor())
    async def scenario():
        return await asyncio.wait_for(server.deliver_command(Command(command="send_text", session_id="s", expected_revision=1, payload={"text": "test"})), 0.5)
    result = asyncio.run(scenario())
    assert result["code"] == 504 and "unknown" in result["error"].lower()
    assert len(sends) == 1
    assert state.queue[0].status == "pending"
    assert state.sessions["s"].status == "ready"
    assert not server.pending_commands and not server.busy_sessions
