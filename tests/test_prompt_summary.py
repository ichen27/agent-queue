import pytest

from monitor.patterns import extract_last_prompt


@pytest.mark.parametrize("output", [
    "Use the ❯ marker to enter a follow-up.",
    "print('❯ not a user request')",
    "> ❯ quoted example",
])
def test_inline_markers_do_not_replace_last_request(output):
    assert extract_last_prompt(f"❯ Fix the timeout\n{output}\n❯ ") == "Fix the timeout"


def test_output_without_a_prompt_has_no_summary():
    assert extract_last_prompt("The ❯ symbol is part of the interface.") == ""


def test_indented_colored_prompt_preserves_marker_in_request():
    output = "❯ Old request\n  \x1b[32m❯\x1b[0m Explain the ❯ symbol\n❯ "
    assert extract_last_prompt(output) == "Explain the ❯ symbol"


def test_long_prompt_stays_bounded_after_ignoring_output_marker():
    request = "x" * 100
    output = f"  ❯ {request}\nUse ❯ for input.\n❯ "
    assert extract_last_prompt(output) == "x" * 77 + "..."
