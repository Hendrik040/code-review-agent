"""Convert an agent trace file into a readable analysis trail.

The mapping table below is THE ONLY PLACE internal tool names like
`build_review_context` or `ast_search` appear in user-visible output.
Trail bullets are what the GitHub review summary shows under "Analysis
trail" — they must read as plain operator language, not jargon.

Trace format (agent_sdk/traces/run_NNN.txt):
  Each tool call is recorded inside a box as two parts:
    │ tool_use: <name>
    │   args: {json-fragment...}
    │ <continuation lines if json is long>
  Continuation lines after `│   args:` start with `│ ` (pipe + space,
  no leading spaces). The box closes with `└─...┘`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Matches the tool_use line inside a trace box.
_TOOL_USE_RE = re.compile(r"^\│ tool_use: (\S+)\s*$")

# Matches the first args line (may be incomplete JSON).
_ARGS_START_RE = re.compile(r"^\│   args: (.+)$")

# Matches a continuation line inside the box (starts with │ + space,
# NOT the deeper-indented args prefix).
_ARGS_CONT_RE = re.compile(r"^\│ (.+)$")

# Box-close sentinel — stop collecting args at this line.
_BOX_CLOSE_RE = re.compile(r"^└─")

# Strip the MCP reviewer prefix so the mapping table works on bare tool names.
_MCP_PREFIX = "mcp__reviewer__"


def _strip_prefix(name: str) -> str:
    """Remove the mcp__reviewer__ prefix if present, else return as-is."""
    if name.startswith(_MCP_PREFIX):
        return name[len(_MCP_PREFIX):]
    return name


def _describe_tool_call(tool_name: str, args: dict) -> str | None:
    """Map a (tool_name, args) pair to a one-line operator-language bullet.

    Returns None for tool calls we deliberately omit (terminal calls,
    unknown tools). Never raises on bad inputs — defensive.
    """
    if tool_name == "build_review_context":
        return "Loaded the PR diff and surrounding context"

    if tool_name == "read_file_section":
        path = args.get("path", "<unknown>")
        start = args.get("start_line", "?")
        end = args.get("end_line", "?")
        return f"Read {path} (lines {start}-{end})"

    if tool_name == "ast_search":
        pattern = args.get("pattern", "")
        m = re.match(r"class\s+(\w+)", pattern)
        if m:
            return (
                f"Searched the codebase for the {m.group(1)} class definition"
            )
        m = re.match(r"def\s+(\w+)", pattern)
        if m:
            return (
                f"Searched the codebase for the {m.group(1)} function definition"
            )
        return "Searched the codebase using a structural pattern"

    if tool_name == "grep":
        pattern = args.get("pattern", "")
        return f"Looked for `{pattern}` in the codebase"

    if tool_name == "bash":
        cmd = args.get("command", "")
        if cmd.startswith("git diff"):
            return "Inspected which files the PR changes"
        return "Ran a shell command on the working tree"

    if tool_name == "write_file":
        path = args.get("path", "<unknown>")
        return f"Wrote scratch notes to {path}"

    # Terminal calls and unknown tools: omit from the trail.
    return None


def _parse_trace(text: str) -> list[tuple[str, dict]]:
    """Extract (tool_name, args_dict) tuples from the trace text.

    Uses a line-by-line state machine to handle multi-line wrapped args.
    Robust to malformed/truncated JSON (skips that entry). Never raises.
    """
    out: list[tuple[str, dict]] = []
    current_name: str | None = None
    collecting_args: bool = False
    args_fragments: list[str] = []

    def _flush() -> None:
        """Try to parse collected args and append to out."""
        nonlocal current_name, collecting_args, args_fragments
        if current_name is not None and args_fragments:
            raw = "".join(args_fragments).strip()
            try:
                args = json.loads(raw)
                if isinstance(args, dict):
                    bare = _strip_prefix(current_name)
                    out.append((bare, args))
            except (json.JSONDecodeError, TypeError):
                pass  # truncated or malformed — skip silently
        current_name = None
        collecting_args = False
        args_fragments = []

    for line in text.splitlines():
        # Box-close: finish any in-progress tool_use block.
        if _BOX_CLOSE_RE.match(line):
            _flush()
            continue

        # New tool_use line: flush previous (if any) and start fresh.
        m = _TOOL_USE_RE.match(line)
        if m:
            _flush()
            current_name = m.group(1)
            continue

        # Start of args.
        if current_name is not None and not collecting_args:
            m = _ARGS_START_RE.match(line)
            if m:
                collecting_args = True
                args_fragments = [m.group(1)]
                continue

        # Continuation args line.
        if collecting_args:
            m = _ARGS_CONT_RE.match(line)
            if m:
                args_fragments.append(m.group(1))
            else:
                # Non-matching line while collecting = end of args block.
                _flush()

    # End of file: flush any dangling block.
    _flush()
    return out


def extract_trail(trace_path: Path, max_bullets: int = 8) -> list[str]:
    """Read a trace file, return up to `max_bullets` friendly bullets.

    Deduplicates consecutive duplicates. Returns [] if the file is
    missing or unparseable — never raises (the caller treats empty
    result as "no trail to show").
    """
    try:
        text = Path(trace_path).read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return []

    bullets: list[str] = []
    for name, args in _parse_trace(text):
        described = _describe_tool_call(name, args)
        if described is None:
            continue
        if bullets and bullets[-1] == described:
            continue  # consecutive dup
        bullets.append(described)
        if len(bullets) >= max_bullets:
            break
    return bullets
