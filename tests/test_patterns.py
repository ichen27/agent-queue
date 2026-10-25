import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from monitor.patterns import detect_state

def test_detects_permission_prompt_allow_deny():
    output = """Here's what I found in the codebase.

  Allow  Deny  """
    result = detect_state(output)
    assert result == "permission_prompt"

def test_detects_permission_prompt_yes_no():
    output = """Do you want to proceed?

  Yes  No  """
    result = detect_state(output)
    assert result == "permission_prompt"

def test_detects_claude_input_prompt():
    output = """Done! The file has been updated.

❯ """
    result = detect_state(output)
    assert result == "ready"

def test_detects_claude_input_prompt_dollar():
    output = """Finished running tests.

$ """
    result = detect_state(output)
    assert result == "ready"

def test_detects_question():
    output = """I found two approaches. Should I use the factory pattern or the builder pattern?"""
    result = detect_state(output)
    assert result == "needs_input"

def test_streaming_output():
    output = """Let me check the file structure and understand the codebase.

Reading src/main.py..."""
    result = detect_state(output)
    assert result == "working"

def test_empty_output():
    result = detect_state("")
    assert result == "working"

def test_extracts_tail_output():
    from monitor.patterns import extract_tail
    lines = "\n".join(f"line {i}" for i in range(100))
    tail = extract_tail(lines, 50)
    assert tail.startswith("line 50")
    assert tail.endswith("line 99")
    assert len(tail.split("\n")) == 50


def test_last_prompt_keeps_single_character_reply():
    from monitor.patterns import extract_last_prompt

    assert extract_last_prompt("❯ Previous request\n❯ y\n❯ ") == "y"


def test_last_prompt_keeps_single_character_unicode_reply():
    from monitor.patterns import extract_last_prompt

    assert extract_last_prompt("❯ Previous request\n❯ 好\n❯ ") == "好"
