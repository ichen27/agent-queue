"""A snapshot error must not interrupt monitor-disconnect notifications."""
import asyncio
from contextlib import nullcontext

import pytest
from starlette.websockets import WebSocketDisconnect

import server.main as server
from server.models import Command, MonitorEvent
from server.state import StateManager


@pytest.mark.parametrize("save_fails", [False, True])
def test_disconnect_notifies_commands_and_dashboards_despite_save_failure(monkeypatch, save_fails):
    state = StateManager()
    state.process_event(MonitorEvent(
        session_id="s", tab_name="Example", event_type="ready", tail_output="Captured",
    ))
    monkeypatch.setattr(server, "state", state)
    monkeypatch.setattr(server, "monitor_ws", None)
    monkeypatch.setattr(server, "pending_commands", {})
    monkeypatch.setattr(server, "busy_sessions", set())
    snapshots = []

    class Dashboard:
        async def send_json(self, message):
            snapshots.append(message)

    monkeypatch.setattr(server, "dashboard_clients", [Dashboard()])

    if save_fails:
        def fail_save():
            raise OSError("Storage unavailable")
        monkeypatch.setattr(state, "save", fail_save)

    async def scenario():
        listening, sent, disconnect = asyncio.Event(), asyncio.Event(), asyncio.Event()

        class Monitor:
            headers = {}

            async def accept(self):
                pass

            async def receive_json(self):
                listening.set()
                await disconnect.wait()
                raise WebSocketDisconnect()

            async def send_json(self, message):
                sent.set()  # Terminal delivery deliberately has no acknowledgement.

        handler = asyncio.create_task(server.monitor_websocket(Monitor()))
        delivery = None
        completed = asyncio.get_running_loop().create_future()
        completed.set_result({"ok": True})
        server.pending_commands["already_done"] = completed
        try:
            await asyncio.wait_for(listening.wait(), 1)
            delivery = asyncio.create_task(server.deliver_command(Command(
                command="focus_tab", session_id="s", command_id="inflight",
            )))
            await asyncio.wait_for(sent.wait(), 1)
            disconnect.set()
            # Preserve the storage failure for server diagnostics.
            with pytest.raises(OSError, match="Storage unavailable") if save_fails else nullcontext():
                await asyncio.wait_for(handler, 1)

            assert server.monitor_ws is None
            assert not state.sessions["s"].available
            assert state.sessions["s"].tail_output == "Captured"
            assert snapshots[-1]["monitor_connected"] is False
            assert snapshots[-1]["sessions"]["s"]["available"] is False
            result = await asyncio.wait_for(delivery, 1)
            assert not result["ok"] and result["code"] == 504
            assert "Delivery unknown" in result["error"]
            assert not server.busy_sessions
            assert set(server.pending_commands) == {"already_done"}
            assert completed.result() == {"ok": True}
        finally:
            tasks = [handler] + ([delivery] if delivery else [])
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(scenario())
