"""Native-operation failures must be acknowledged without exposing native error text."""
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.mark.parametrize("failure", [RuntimeError, OSError])
def test_monitor_acknowledges_failed_operation_and_processes_next_command(monkeypatch, failure):
    monkeypatch.setitem(sys.modules, "iterm2", ModuleType("iterm2"))
    monkeypatch.setattr(sys, "path", sys.path.copy())
    path = Path(__file__).resolve().parents[1] / "monitor" / "claude_monitor.py"
    spec = importlib.util.spec_from_file_location("monitor_ack_fixture", path)
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)

    calls, acknowledgements = [], []
    private_detail = "synthetic-private-native-error"

    async def rename(name):
        calls.append(("rename", name))
        raise failure(private_detail)

    async def activate_tab():
        calls.append(("tab",))

    async def activate_window():
        calls.append(("window",))

    tab = SimpleNamespace(
        sessions=[SimpleNamespace(session_id="s")],
        async_set_title=rename, async_activate=activate_tab,
    )
    app = SimpleNamespace(terminal_windows=[
        SimpleNamespace(tabs=[tab], async_activate=activate_window),
    ])
    incoming = [
        {"type": "error", "error": "Invalid monitor message"},
        {"command": "rename_tab", "command_id": "rename", "session_id": "s",
         "payload": {"name": "Example"}},
        {"command": "focus_tab", "command_id": "focus", "session_id": "s"},
    ]

    class Connection:
        async def __aiter__(self):
            for message in incoming:
                yield json.dumps(message)

        async def send(self, raw):
            acknowledgements.append(json.loads(raw))

    asyncio.run(monitor.handle_commands(Connection(), app))

    assert calls == [("rename", "Example"), ("tab",), ("window",)]
    assert acknowledgements == [
        {"type": "command_ack", "command_id": "rename", "ok": False,
         "error": "iTerm2 could not confirm this operation. Check the terminal."},
        {"type": "command_ack", "command_id": "focus", "ok": True},
    ]
    assert private_detail not in json.dumps(acknowledgements)
