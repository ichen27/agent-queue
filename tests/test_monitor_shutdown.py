"""Stopping the monitor must await both workers and close their shared socket."""
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


@pytest.mark.parametrize("trigger", ["cancel", "poll_return", "command_error"])
@pytest.mark.parametrize("close_fails", [False, True])
def test_monitor_cleans_up_workers_and_socket(monkeypatch, trigger, close_fails):
    monkeypatch.setitem(sys.modules, "iterm2", ModuleType("iterm2"))
    monkeypatch.setattr(sys, "path", sys.path.copy())
    path = Path(__file__).resolve().parents[1] / "monitor" / "claude_monitor.py"
    spec = importlib.util.spec_from_file_location("monitor_shutdown_fixture", path)
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)

    async def scenario():
        started = [asyncio.Event(), asyncio.Event()]
        stopped = [asyncio.Event(), asyncio.Event()]
        release = asyncio.Event()
        closed = asyncio.Event()
        workers = []
        connections = 0
        close_calls = 0

        class Connection:
            async def close(self):
                nonlocal close_calls
                close_calls += 1
                assert all(event.is_set() for event in stopped)
                closed.set()
                if close_fails:
                    raise OSError("synthetic close failure")

        ws = Connection()
        app = object()

        async def get_app(connection):
            return app

        async def connect():
            nonlocal connections
            connections += 1
            return ws

        async def worker(index, socket, native_app):
            assert socket is ws and native_app is app
            workers.append(asyncio.current_task())
            started[index].set()
            try:
                await release.wait()
                if trigger == "poll_return" and index == 0:
                    return
                if trigger == "command_error" and index == 1:
                    raise RuntimeError("synthetic worker failure")
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)  # Cleanup must be awaited, not just requested.
                stopped[index].set()

        async def poll(socket, native_app):
            await worker(0, socket, native_app)

        async def commands(socket, native_app):
            await worker(1, socket, native_app)

        monkeypatch.setattr(monitor.iterm2, "async_get_app", get_app, raising=False)
        monkeypatch.setattr(monitor, "connect_to_server", connect)
        monkeypatch.setattr(monitor, "poll_sessions", poll)
        monkeypatch.setattr(monitor, "handle_commands", commands)
        task = asyncio.create_task(monitor.main(object()))
        try:
            for event in started:
                await asyncio.wait_for(event.wait(), 1)
            if trigger == "cancel":
                task.cancel()
            else:
                release.set()
                await asyncio.wait_for(closed.wait(), 1)
                task.cancel()  # Stop during the reconnect delay.
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 1)
            assert all(event.is_set() for event in stopped)
            assert all(worker.done() for worker in workers)
            assert closed.is_set()
            assert close_calls == 1
            assert connections == 1
        finally:
            # A failing regression must not leave its own workers running.
            task.cancel()
            for worker_task in workers:
                worker_task.cancel()
            await asyncio.gather(task, *workers, return_exceptions=True)

    asyncio.run(scenario())
