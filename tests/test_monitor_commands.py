import asyncio
from types import SimpleNamespace
import pytest
from monitor.commands import execute_command

OUTPUT = "[Claude 4.0]\nDone.\n❯ "


def run_command(output=OUTPUT, expected=OUTPUT, text="Add tests", job="claude"):
    sent = []
    async def send(value):
        sent.append(value)
    async def read(session):
        return output
    async def variable(name):
        return job
    session = SimpleNamespace(session_id="s1", async_send_text=send, async_get_variable=variable)
    app = SimpleNamespace(terminal_windows=[SimpleNamespace(tabs=[SimpleNamespace(sessions=[session])])])
    asyncio.run(execute_command({"command": "send_text", "session_id": "s1", "payload": {"text": text}, "expected_output": expected}, app, read))
    return sent


def test_monitor_confirms_plain_single_line_reply():
    assert run_command() == ["Add tests\r"]


def test_monitor_rejects_changed_terminal_before_typing():
    with pytest.raises(ValueError, match="changed"):
        run_command(output=OUTPUT + "new output")


def test_monitor_rejects_shell_even_with_old_signature():
    output = "[Claude 4.0]\nExiting Claude\nuser@host project % "
    with pytest.raises(ValueError, match="not waiting"):
        run_command(output=output, expected=output)


def test_monitor_never_replies_to_permission_prompt():
    output = "[Claude 4.0]\nAllow Deny"
    with pytest.raises(ValueError, match="not waiting"):
        run_command(output=output, expected=output, text="y")

def test_monitor_rejects_shell_dollar_prompt_with_old_claude_signature():
    output = "[Claude 4.0]\nExited.\n$ "
    with pytest.raises(ValueError, match="not waiting"):
        run_command(output=output, expected=output)


def test_monitor_rejects_stale_claude_prompt_above_shell():
    output = "[Claude 4.0]\n❯ \nExited.\n$ "
    with pytest.raises(ValueError, match="not waiting"):
        run_command(output=output, expected=output)

@pytest.mark.parametrize("job", ["zsh", "bash", "fish", "node", "", None])
def test_stale_claude_signature_and_shell_arrow_never_receive_text(job):
    output = "[Claude 4.0]\nExited Claude.\n❯ "
    with pytest.raises(ValueError, match="foreground"):
        run_command(output=output, expected=output, job=job)
