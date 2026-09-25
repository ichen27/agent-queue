import re

# --- Claude Code session detection ---
_CLAUDE_CODE_SIGNATURES = [
    re.compile(r"Context\s+[█░]+\s+\d+%"),
    re.compile(r"\[(?:Opus|Sonnet|Haiku|Claude)\s+[\d.]+\]", re.IGNORECASE),
    re.compile(r"bypass permissions", re.IGNORECASE),
    re.compile(r"Co-Authored-By:.*Claude"),
]


def is_claude_code_session(output: str) -> bool:
    if not output.strip():
        return False
    for pattern in _CLAUDE_CODE_SIGNATURES:
        if pattern.search(output):
            return True
    return False


# --- State detection ---

_PERMISSION_PATTERNS = [
    re.compile(r"Allow\s+Deny", re.IGNORECASE),
    re.compile(r"^\s*Yes\s+No\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\(y/n\)", re.IGNORECASE),
]

_READY_PATTERN = re.compile(r"─{5,}\s*\n\s*❯")


def detect_state(output: str, content_changed: bool = False) -> str:
    """Detect Claude Code state from terminal output.

    Args:
        output: terminal text
        content_changed: True if the terminal content changed since last poll.
            When content is actively changing, Claude is still working even if
            a ❯ prompt is visible in the buffer from a previous turn.
    """
    if not output.strip():
        return "working"

    lines = output.strip().split("\n")
    # Only look at the last 8 lines for state detection — avoids matching
    # prompts/patterns from earlier turns still in scrollback
    tail = "\n".join(lines[-8:])

    # If content just changed, Claude is likely still streaming output.
    # Only override if we DON'T see a clear finished signal in the last lines.
    if content_changed:
        # Even if content changed, permission prompts are immediate
        for pattern in _PERMISSION_PATTERNS:
            if pattern.search(tail):
                return "permission_prompt"
        # Content still changing = still working
        return "working"

    # Permission prompts (highest priority)
    for pattern in _PERMISSION_PATTERNS:
        if pattern.search(tail):
            return "permission_prompt"

    # Ready prompt: ❯ after a separator in the tail
    if _READY_PATTERN.search(tail) or re.search(r"^\s*[❯$]\s*$", tail, re.MULTILINE):
        if re.search(r"Context\s+░{5,}\s+0%", tail):
            return "idle"
        return "ready"

    # Check for question in last meaningful line
    for line in reversed(lines[-8:]):
        stripped = line.strip()
        if not stripped:
            continue
        if _is_chrome_line(stripped):
            continue
        if "?" in stripped:
            return "needs_input"
        break

    return "working"


# --- Chrome detection and stripping ---

_CHROME_PATTERNS = [
    re.compile(r"^\s*─{5,}\s*$"),                           # separator lines
    re.compile(r"^\s*❯"),                                     # prompt line
    re.compile(r"^\s*\[(?:Opus|Sonnet|Haiku|Claude)\s"),     # model info
    re.compile(r"^\s*Context\s+[█░]+"),                       # context bar
    re.compile(r"^\s*⏵⏵\s*bypass permissions"),              # permission mode
    re.compile(r"^\s*✻"),                                     # timing decorator
    re.compile(r"^\s*(Worked|Baked|Sautéed|Brewed) for \d"),  # timing line
    re.compile(r"new task\?", re.IGNORECASE),                 # new task prompt
]


def _is_chrome_line(line: str) -> bool:
    for p in _CHROME_PATTERNS:
        if p.search(line):
            return True
    return False


# ANSI escape code pattern
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b\[.*?[@-~]")
# Control characters (except newline, tab, and null which we handle separately)
_CTRL_RE = re.compile(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_output(text: str) -> str:
    """Strip ANSI codes and fix iTerm2 null-byte spacing."""
    text = _ANSI_RE.sub("", text)
    text = text.replace("\x00", " ")
    text = text.replace("\xa0", " ")
    text = _CTRL_RE.sub("", text)
    return text


def strip_chrome(text: str) -> str:
    """Remove Claude Code UI chrome lines from output, keep terminal formatting."""
    lines = text.split("\n")
    kept = []
    # Walk from end, skip trailing chrome block
    i = len(lines) - 1
    trailing_chrome = True
    while i >= 0:
        line = lines[i]
        if trailing_chrome:
            stripped = line.strip()
            if not stripped or _is_chrome_line(stripped):
                i -= 1
                continue
            trailing_chrome = False
        kept.append(lines[i])
        i -= 1
    kept.reverse()

    # Also strip chrome lines from the middle (between turns)
    result = []
    skip_block = False
    for line in kept:
        stripped = line.strip()
        if re.match(r"─{5,}", stripped):
            skip_block = True
            continue
        if skip_block:
            if _is_chrome_line(stripped) or not stripped:
                continue
            skip_block = False
        result.append(line)

    # Collapse runs of 3+ blank lines to 2
    final = []
    blank_count = 0
    for line in result:
        if not line.strip():
            blank_count += 1
            if blank_count <= 2:
                final.append(line)
        else:
            blank_count = 0
            final.append(line)

    return "\n".join(final).strip()


_PROMPT_RE = re.compile(r"❯\s*(.+)")


def extract_last_prompt(text: str) -> str:
    """Find the last user prompt (text after ❯) in terminal output."""
    cleaned = clean_output(text)
    lines = cleaned.split("\n")
    # Walk backwards to find the last ❯ line with actual text
    for line in reversed(lines):
        m = _PROMPT_RE.search(line.strip())
        if m:
            prompt = m.group(1).strip()
            if prompt and len(prompt) > 1:
                # Truncate long prompts
                if len(prompt) > 80:
                    return prompt[:77] + "..."
                return prompt
    return ""


def extract_tail(text: str, lines: int = 50) -> str:
    """Return a bounded terminal excerpt."""
    return "\n".join(text.splitlines()[-lines:]) if lines > 0 else ""


def has_reply_prompt(output: str) -> bool:
    """Require a current empty Claude prompt, not a shell or an old scrollback prompt."""
    lines = clean_output(output).splitlines()[-8:]
    for line in reversed(lines):
        value = line.strip()
        if re.fullmatch(r"❯\s*", value):
            return True
        if value and not _is_chrome_line(value):
            return False
    return False
