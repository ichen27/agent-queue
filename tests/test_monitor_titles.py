"""Native tab names must not prevent otherwise valid observations reaching the relay."""
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from server.models import MonitorEvent


@pytest.mark.parametrize("title", ["Example", "x" * 200, "x" * 201, "界" * 201, None, RuntimeError("lookup failed")],
                         ids=["short", "limit", "long_ascii", "long_unicode", "fallback", "lookup_failure"])
def test_monitor_emits_valid_events_despite_native_tab_title_limits_or_failure(monkeypatch, title):
    # Polling does not need the optional macOS SDK; substitute only its import.
    monkeypatch.setitem(sys.modules, "iterm2", ModuleType("iterm2"))
    monkeypatch.setattr(sys, "path", sys.path.copy())
    path = Path(__file__).resolve().parents[1] / "monitor" / "claude_monitor.py"
    spec = importlib.util.spec_from_file_location("monitor_title_fixture", path)
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)

    output = "[Claude 4.0]\nCaptured output\n❯ "
    messages = []

    async def read_contents(session):
        return output

    async def get_variable(name):
        assert name == "titleOverride"
        if isinstance(title, Exception):
            raise title
        return title

    tab = SimpleNamespace(
        tab_id="fallback-tab", async_get_variable=get_variable,
        sessions=[SimpleNamespace(session_id="s")],
    )
    async def get_next_title(name):
        return "Next tab"

    next_tab = SimpleNamespace(
        tab_id="next-tab", async_get_variable=get_next_title,
        sessions=[SimpleNamespace(session_id="next")],
    )
    app = SimpleNamespace(terminal_windows=[SimpleNamespace(tabs=[tab, next_tab])])
    monkeypatch.setattr(monitor, "read_session_contents", read_contents)

    class Connection:
        async def send(self, raw):
            message = json.loads(raw)
            messages.append(message)
            if message.get("type") == "inventory":
                raise asyncio.CancelledError  # Stop after one complete polling pass.

    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(monitor.poll_sessions(Connection(), app), 1)

    asyncio.run(scenario())
    assert len(messages) == 3
    event = MonitorEvent.model_validate(messages[0])
    assert event.session_id == "s"
    assert event.tab_name == (title if isinstance(title, str) else "fallback-tab")[:200]
    assert event.full_output == output
    assert event.event_type == "working"
    next_event = MonitorEvent.model_validate(messages[1])
    assert next_event.session_id == "next"
    assert next_event.tab_name == "Next tab"
    assert next_event.full_output == output
    assert messages[2] == {"type": "inventory", "session_ids": ["s", "next"]}
