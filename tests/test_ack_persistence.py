"""A disk error after terminal acknowledgement must not make a reply reusable."""
import asyncio

import server.main as server
from server.models import Command, MonitorEvent
from server.state import StateManager


def test_acknowledged_reply_invalidates_revision_even_if_snapshot_save_fails(monkeypatch):
    state = StateManager()
    state.process_event(MonitorEvent(
        session_id="s", tab_name="Example", event_type="ready", full_output="Captured output",
    ))
    monkeypatch.setattr(server, "state", state)
    monkeypatch.setattr(server, "dashboard_clients", [])
    monkeypatch.setattr(server, "pending_commands", {})
    monkeypatch.setattr(server, "busy_sessions", set())
    sent = []

    class Monitor:
        async def send_json(self, message):
            sent.append(message)
            server.pending_commands[message["command_id"]].set_result({"ok": True})

    def fail_save():
        raise OSError("Storage unavailable")

    monkeypatch.setattr(server, "monitor_ws", Monitor())
    monkeypatch.setattr(state, "save", fail_save)

    async def scenario():
        result = await server.deliver_command(Command(
            command="send_text", session_id="s", expected_revision=1,
            payload={"text": "Continue"},
        ))
        assert result["ok"] is False and result["code"] == 504
        assert len(sent) == 1
        # iTerm2 already accepted the reply, even though its snapshot could not save.
        assert state.queue[0].status == "resolved"
        assert state.sessions["s"].status == "working"
        assert state.sessions["s"].revision == 2
        assert not server.pending_commands and not server.busy_sessions

        repeated = await server.deliver_command(Command(
            command="send_text", session_id="s", expected_revision=1,
            payload={"text": "Continue"},
        ))
        assert repeated["ok"] is False and repeated["code"] == 409
        assert "changed" in repeated["error"]
        assert len(sent) == 1

    asyncio.run(scenario())
