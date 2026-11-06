import pytest

from monitor.patterns import has_reply_prompt, strip_chrome


@pytest.mark.parametrize("line", [
    "Would you like a new task? Review the current changes first.",
    'print("new task?")',
    "new task? Keep this explanation visible.",
])
def test_inline_new_task_question_remains_captured_output(line):
    output = f"Useful output\n{line}\n\n❯ \nnew task?"
    assert strip_chrome(output) == f"Useful output\n{line}"
    assert not has_reply_prompt(f"[Claude 4.0]\n❯ \n{line}")


@pytest.mark.parametrize("chrome", ["new task?", "  New Task?  "])
def test_standalone_new_task_chrome_is_still_removed(chrome):
    output = f"[Claude 4.0]\nUseful output\n❯ \n{chrome}"
    assert strip_chrome(output) == "[Claude 4.0]\nUseful output"
    assert has_reply_prompt(output)
