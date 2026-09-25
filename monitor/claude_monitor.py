#!/usr/bin/env python3
"""
Agent Queue — iTerm2 Monitor Script

Local script that watches all iTerm2 sessions for Claude Code activity
and pushes events to the backend server via WebSocket.
"""

import asyncio
import json
import time
import iterm2
import websockets

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from monitor.commands import execute_command
from monitor.patterns import detect_state, clean_output, strip_chrome, is_claude_code_session, extract_last_prompt

SERVER_URL = os.environ.get("AGENT_QUEUE_MONITOR_URL", "ws://127.0.0.1:7890/ws/monitor")
POLL_INTERVAL = 2.0

_prev_content: dict[str, str] = {}
_prev_state: dict[str, str] = {}
_last_change_time: dict[str, float] = {}

NUM_LINES_TO_READ = 200  # Read last N lines from each session


async def read_session_contents(session) -> str:
    """Read terminal contents from a session using the iTerm2 API."""
    line_info = await session.async_get_line_info()
    overflow = line_info.overflow
    total = line_info.mutable_area_height + line_info.scrollback_buffer_height
    first_line = max(overflow, total - NUM_LINES_TO_READ + overflow)
    num_lines = min(NUM_LINES_TO_READ, total - (first_line - overflow))
    if num_lines <= 0:
        return ""
    contents = await session.async_get_contents(first_line, num_lines)
    # Respect soft-wrap: only insert \n at hard newlines, use space at soft wraps
    parts = []
    for i, line in enumerate(contents):
        text = line.string.rstrip()
        parts.append(text)
        if i < len(contents) - 1:
            # hard_newline=False means line is soft-wrapped continuation
            if line.hard_eol:
                parts.append("\n")
            else:
                # Add space at soft-wrap boundary to preserve word spacing
                if text and not text.endswith(" "):
                    parts.append(" ")
    return "".join(parts)


async def connect_to_server():
    while True:
        try:
            ws = await websockets.connect(SERVER_URL)
            print(f"[monitor] Connected to {SERVER_URL}")
            return ws
        except Exception as e:
            print(f"[monitor] Connection failed ({e}), retrying in 3s...")
            await asyncio.sleep(3)


async def handle_commands(ws, app):
    async for raw in ws:
        data = json.loads(raw)
        if "command" not in data:
            continue
        ack = {"type": "command_ack", "command_id": data.get("command_id"), "ok": False}
        try:
            await execute_command(data, app, read_session_contents)
            ack["ok"] = True
        except Exception as exc:
            # Do not log reply contents or terminal history.
            ack["error"] = str(exc) if isinstance(exc, ValueError) else "iTerm2 could not confirm this operation. Check the terminal."
        await ws.send(json.dumps(ack))


async def poll_sessions(ws, app):
    last_refresh = 0.0
    while True:
        try:
            now = time.time()
            refresh = now - last_refresh >= 10
            active_ids = []

            for window in app.terminal_windows:
                for tab in window.tabs:
                    tab_name = await tab.async_get_variable("titleOverride") or tab.tab_id
                    for session in tab.sessions:
                        sid = session.session_id

                        try:
                            full_text = await read_session_contents(session)
                        except Exception:
                            continue

                        if not is_claude_code_session(full_text):
                            # Not a Claude Code session — skip
                            if sid in _prev_state:
                                del _prev_state[sid]
                            continue

                        active_ids.append(sid)
                        prev = _prev_content.get(sid, "")
                        content_changed = full_text != prev
                        if content_changed:
                            _prev_content[sid] = full_text
                            _last_change_time[sid] = now

                        state = detect_state(full_text, content_changed=content_changed)

                        prev_state = _prev_state.get(sid)
                        state_changed = state != prev_state
                        if state_changed:
                            _prev_state[sid] = state

                        # Send update on state change OR content change
                        if state_changed or content_changed or refresh:
                            cleaned = clean_output(full_text)[-100_000:]
                            stripped = strip_chrome(cleaned)
                            event = {
                                "session_id": sid,
                                "tab_name": str(tab_name),
                                "event_type": state,
                                "tail_output": stripped,
                                "summary": extract_last_prompt(full_text),
                                "full_output": cleaned,
                                "timestamp": now,
                            }

                            try:
                                await ws.send(json.dumps(event))
                            except websockets.ConnectionClosed:
                                print("[monitor] Lost connection while sending")
                                return

            await ws.send(json.dumps({"type": "inventory", "session_ids": active_ids}))
            for cache in (_prev_content, _prev_state, _last_change_time):
                for sid in set(cache) - set(active_ids):
                    cache.pop(sid, None)
            if refresh:
                last_refresh = now
        except websockets.ConnectionClosed:
            return
        except Exception as e:
            print(f"[monitor] Poll error: {type(e).__name__}")

        await asyncio.sleep(POLL_INTERVAL)


async def main(connection):
    app = await iterm2.async_get_app(connection)
    if not app:
        print("[monitor] Could not get iTerm2 app")
        return

    print("[monitor] Starting Agent Queue monitor")

    while True:
        ws = await connect_to_server()
        _prev_content.clear()
        _prev_state.clear()

        poll_task = asyncio.create_task(poll_sessions(ws, app))
        cmd_task = asyncio.create_task(handle_commands(ws, app))

        done, pending = await asyncio.wait(
            [poll_task, cmd_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)

        try:
            await ws.close()
        except Exception:
            pass

        print("[monitor] Reconnecting in 3s...")
        await asyncio.sleep(3)


if __name__ == "__main__":
    iterm2.run_forever(main)
