"""Periodic observations must follow elapsed time, independently of clock corrections."""
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from server.models import MonitorEvent


@pytest.mark.parametrize("wall_times", [
    [1000, 1002, 1009, 1010, 1020],
    [1000, 1002, 900, 901, 911],
    [1000, 5000, 5007, 5008, 5018],
], ids=["steady_clock", "backward_jump", "forward_jump"])
def test_unchanged_sessions_refresh_on_elapsed_time(monkeypatch, wall_times):
    monkeypatch.setitem(sys.modules, "iterm2", ModuleType("iterm2"))
    monkeypatch.setattr(sys, "path", sys.path.copy())
    path = Path(__file__).resolve().parents[1] / "monitor" / "claude_monitor.py"
    spec = importlib.util.spec_from_file_location("monitor_refresh_fixture", path)
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)

    elapsed_times = [100, 102, 109, 110, 120]
    step = 0
    monkeypatch.setattr(monitor, "time", SimpleNamespace(
        time=lambda: wall_times[step], monotonic=lambda: elapsed_times[step],
    ))
    monkeypatch.setattr(monitor, "POLL_INTERVAL", 0)
    output = "[Claude 4.0]\nCaptured output\n❯ "
    events, inventories = [], []

    async def read_contents(session):
        return output

    async def get_variable(name):
        return "Example"

    monkeypatch.setattr(monitor, "read_session_contents", read_contents)
    tab = SimpleNamespace(
        tab_id="tab", async_get_variable=get_variable,
        sessions=[SimpleNamespace(session_id="s")],
    )
    app = SimpleNamespace(terminal_windows=[SimpleNamespace(tabs=[tab])])

    class Connection:
        async def send(self, raw):
            nonlocal step
            message = json.loads(raw)
            if message.get("type") == "inventory":
                inventories.append(message)
                if step == len(elapsed_times) - 1:
                    raise asyncio.CancelledError
                step += 1
            else:
                events.append((step, MonitorEvent.model_validate(message)))

    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(monitor.poll_sessions(Connection(), app), 1)

    asyncio.run(scenario())
    # Initial observation, settled state, then refreshes at 10 and 20 elapsed seconds.
    assert [index for index, _ in events] == [0, 1, 3, 4]
    assert [event.event_type for _, event in events] == ["working", "ready", "ready", "ready"]
    assert [event.timestamp for _, event in events] == [wall_times[i] for i in [0, 1, 3, 4]]
    assert all(event.full_output == output for _, event in events)
    assert inventories == [{"type": "inventory", "session_ids": ["s"]}] * 5
