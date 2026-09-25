"""Terminal command boundary, kept independent of the iTerm2 import for testing."""
from monitor.patterns import clean_output, detect_state, is_claude_code_session, has_reply_prompt
from server.models import Command


async def execute_command(data, app, read_contents):
    command = Command(**data)
    found = next(((window, tab, session) for window in app.terminal_windows for tab in window.tabs for session in tab.sessions if session.session_id == command.session_id), None)
    if not found:
        raise ValueError("Session is no longer open. Nothing was sent.")
    window, tab, session = found
    if command.command == "send_text":
        output = await read_contents(session)
        # The backend view can lag. Never type into a changed prompt or a shell.
        if clean_output(output)[-100_000:] != data.get("expected_output") or not is_claude_code_session(output):
            raise ValueError("Terminal changed. Review it in iTerm2 before retrying.")
        if detect_state(output) not in ("ready", "needs_input") or not has_reply_prompt(output):
            raise ValueError("Terminal is not waiting for a reply. Open iTerm2.")
        # iTerm2 owns this foreground-job observation; a shell can reuse ❯ and
        # retain Claude scrollback. Unknown/wrapper process names fail closed.
        job = await session.async_get_variable("jobName")
        if not isinstance(job, str) or job.casefold() != "claude":
            raise ValueError("Cannot confirm Claude as the foreground job. Reply in iTerm2.")
        await session.async_send_text(command.payload["text"] + "\r")
    elif command.command == "focus_tab":
        await tab.async_activate()
        await window.async_activate()
    elif command.command == "rename_tab":
        await tab.async_set_title(command.payload["name"])
    elif command.command == "get_history":
        await read_contents(session)
