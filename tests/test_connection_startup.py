import asyncio
from contextlib import suppress

import pytest
from starlette.websockets import WebSocketDisconnect

import server.main as server
from server.models import MonitorEvent
from server.state import StateManager


@pytest.mark.parametrize("error", [WebSocketDisconnect, RuntimeError, asyncio.CancelledError])
def test_dashboard_initial_snapshot_failure_unregisters_client(monkeypatch, error):
    class Dashboard:
        headers = {}

        async def accept(self):
            pass

        async def send_json(self, message):
            raise error()

    existing = object()
    monkeypatch.setattr(server, "dashboard_clients", [existing])

    async def scenario():
        with suppress(WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
            await server.dashboard_websocket(Dashboard())
        assert server.dashboard_clients == [existing]

    asyncio.run(scenario())


def test_cancelled_monitor_startup_releases_slot_and_invalidates_sessions(monkeypatch):
    state = StateManager()
    state.process_event(MonitorEvent(
        session_id="s", tab_name="tab", event_type="ready", tail_output="Captured",
    ))
    monkeypatch.setattr(server, "state", state)
    monkeypatch.setattr(server, "monitor_ws", None)
    monkeypatch.setattr(server, "pending_commands", {})

    async def scenario():
        started = asyncio.Event()
        snapshots = []

        class Dashboard:
            block_once = True

            async def send_json(self, message):
                if self.block_once:
                    self.block_once = False
                    started.set()
                    await asyncio.Event().wait()
                snapshots.append(message)

        class Monitor:
            headers = {}
            rejected = False

            async def accept(self):
                pass

            async def close(self, **kwargs):
                self.rejected = True

            async def receive_json(self):
                raise WebSocketDisconnect()

        monkeypatch.setattr(server, "dashboard_clients", [Dashboard()])
        pending = asyncio.get_running_loop().create_future()
        server.pending_commands["inflight"] = pending
        task = asyncio.create_task(server.monitor_websocket(Monitor()))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Consume the future in the failing case too, avoiding orphaned futures.
        if not pending.done():
            pending.cancel()
        assert server.monitor_ws is None
        assert not state.sessions["s"].available
        assert state.sessions["s"].tail_output == "Captured"
        assert snapshots[-1]["monitor_connected"] is False
        with pytest.raises(ConnectionError, match="disconnected"):
            await pending

        replacement = Monitor()
        await server.monitor_websocket(replacement)
        assert not replacement.rejected
        assert server.monitor_ws is None

    asyncio.run(scenario())
