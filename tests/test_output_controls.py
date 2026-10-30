import pytest

from monitor.patterns import clean_output, extract_last_prompt


@pytest.mark.parametrize("opening", ["\x07", "\x1b\\"])
@pytest.mark.parametrize("closing", ["\x07", "\x1b\\"])
def test_hyperlink_controls_preserve_visible_label(opening, closing):
    output = (
        "See "
        f"\x1b]8;;https://example.com/docs{opening}"
        "\x1b[32mdocumentation\x1b[0m"
        f"\x1b]8;;{closing}"
        " for details.\nDone."
    )
    assert clean_output(output) == "See documentation for details.\nDone."


@pytest.mark.parametrize("terminator", ["\x07", "\x1b\\"])
def test_title_controls_do_not_contaminate_prompt_summary(terminator):
    output = f"\x1b]0;agent terminal{terminator}❯ Fix the bug"
    assert clean_output(output) == "❯ Fix the bug"
    assert extract_last_prompt(output) == "Fix the bug"
