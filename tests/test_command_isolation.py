"""Concurrent callers must not overlap terminal operations or steal acknowledgements."""
import asyncio

import pytest

import server.main as server
from server.models import Command, MonitorEvent
from server.state import StateManager


@pytest.mark.parametrize("outcome", ["accepted", "rejected", "cancelled"])
def test_delivery_locks_isolate_sessions_and_release_after_completion(monkeypatch, outcome):
    state = StateManager()
    for sid in ("first", "second"):
        state.process_event(MonitorEvent(
            session_id=sid, tab_name=sid, event_type="ready", full_output=sid,
        ))
    monkeypatch.setattr(server, "state", state)
    monkeypatch.setattr(server, "pending_commands", {})
    monkeypatch.setattr(server, "busy_sessions", set())
    monkeypatch.setattr(server, "dashboard_clients", [])
    sent = []

    async def scenario():
        started = asyncio.Event()

        class Monitor:
            async def send_json(self, message):
                sent.append(message)
                if message["command_id"] == "original":
                    started.set()
                else:
                    server.pending_commands[message["command_id"]].set_result({"ok": True})

        monkeypatch.setattr(server, "monitor_ws", Monitor())
        original = asyncio.create_task(server.deliver_command(Command(
            command="send_text", session_id="first", command_id="original",
            expected_revision=1, payload={"text": "Continue"},
        )))
        try:
            await asyncio.wait_for(started.wait(), 1)
            original_ack = server.pending_commands["original"]

            # A second caller cannot overlap an operation on the same terminal.
            busy = await server.deliver_command(Command(
                command="focus_tab", session_id="first", command_id="overlap",
            ))
            assert busy["ok"] is False and busy["code"] == 409
            assert "pending for this session" in busy["error"]

            # Nor can a different terminal reuse the pending acknowledgement ID.
            duplicate = await server.deliver_command(Command(
                command="focus_tab", session_id="second", command_id="original",
            ))
            assert duplicate["ok"] is False and duplicate["code"] == 409
            assert "ID is already in use" in duplicate["error"]
            assert [message["command_id"] for message in sent] == ["original"]
            assert server.pending_commands == {"original": original_ack}
            assert server.busy_sessions == {"first"}

            # An independent operation can finish without releasing the first lock.
            independent = await server.deliver_command(Command(
                command="focus_tab", session_id="second", command_id="independent",
            ))
            assert independent["ok"] is True
            assert not original.done() and not original_ack.done()
            assert server.pending_commands == {"original": original_ack}
            assert server.busy_sessions == {"first"}
            assert all(item.status == "pending" for item in state.queue)

            if outcome == "cancelled":
                original.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await original
            else:
                original_ack.set_result({"ok": outcome == "accepted", "error": "Screen changed"})
                result = await asyncio.wait_for(original, 1)
                assert result["ok"] is (outcome == "accepted")
                if outcome == "rejected":
                    assert result["error"] == "Screen changed"

            assert not server.pending_commands and not server.busy_sessions
            accepted = outcome == "accepted"
            assert state.sessions["first"].status == ("working" if accepted else "ready")
            assert state.sessions["first"].revision == (2 if accepted else 1)
            assert [item.status for item in state.queue] == [
                "resolved" if accepted else "pending", "pending",
            ]

            # Completion releases the terminal for a new explicit operation.
            followup = await server.deliver_command(Command(
                command="focus_tab", session_id="first", command_id="followup",
            ))
            assert followup["ok"] is True
            assert [message["command_id"] for message in sent] == [
                "original", "independent", "followup",
            ]
            assert not server.pending_commands and not server.busy_sessions
        finally:
            if not original.done():
                original.cancel()
            await asyncio.gather(original, return_exceptions=True)

    asyncio.run(scenario())
