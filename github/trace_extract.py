"""Convert an agent trace file into a readable analysis trail.

Internal tool names (build_review_context, ast_search, …) appear ONLY in
the mapping table below — trail bullets use plain operator language.

Trace format: each tool call is a box with `│ tool_use: <name>` and
`│   args: {json}` lines; multi-line args continue on `│ ` lines;
box closes with `└─`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from github._trace_text import sanitize_bash_cmd

_TOOL_USE_RE = re.compile(r"^\│ tool_use: (\S+)\s*$")
_ARGS_START_RE = re.compile(r"^\│   args: (.+)$")
_ARGS_CONT_RE = re.compile(r"^\│ (.+)$")
_BOX_CLOSE_RE = re.compile(r"^└─")
_MCP_PREFIX = "mcp__reviewer__"


def _strip_prefix(name: str) -> str:
    return name[len(_MCP_PREFIX):] if name.startswith(_MCP_PREFIX) else name


def _describe_tool_call(tool_name: str, args: dict) -> str | None:
    """Map (tool_name, args) to an operator-language bullet; None to omit."""
    tool_name = tool_name.lower()

    if tool_name == "build_review_context":
        return "Loaded the PR diff and surrounding context"

    if tool_name == "read_file_section":
        path = args.get("path", "<unknown>")
        return f"Read {path} (lines {args.get('start_line','?')}-{args.get('end_line','?')})"

    if tool_name == "read":
        path = args.get("file_path", args.get("path", "<unknown>"))
        offset = args.get("offset")
        limit = args.get("limit")
        if offset is not None and limit is not None:
            return f"Read {path} (lines {offset}-{offset + limit - 1})"
        return f"Read {path}"

    if tool_name == "glob":
        return f"Searched for files matching `{args.get('pattern', '')}`"

    if tool_name == "ast_search":
        pattern = args.get("pattern", "")
        m = re.match(r"class\s+(\w+)", pattern)
        if m:
            return f"Searched the codebase for the {m.group(1)} class definition"
        m = re.match(r"def\s+(\w+)", pattern)
        if m:
            return f"Searched the codebase for the {m.group(1)} function definition"
        return "Searched the codebase using a structural pattern"

    if tool_name == "grep":
        return f"Looked for `{args.get('pattern', '')}` in the codebase"

    if tool_name == "bash":
        cmd = (args.get("command") or "").strip()
        if cmd.startswith("git diff"):
            return "Inspected which files the PR changes"
        return f"Ran `{sanitize_bash_cmd(cmd)}`"

    if tool_name == "write_file":
        return f"Wrote scratch notes to {args.get('path', '<unknown>')}"

    return None


def _parse_trace(text: str) -> list[tuple[str, dict]]:
    """Extract (tool_name, args_dict) tuples; robust to bad JSON. Never raises."""
    out: list[tuple[str, dict]] = []
    current_name: str | None = None
    collecting_args: bool = False
    args_fragments: list[str] = []

    def _flush() -> None:
        nonlocal current_name, collecting_args, args_fragments
        if current_name is not None and args_fragments:
            raw = "".join(args_fragments).strip()
            try:
                args = json.loads(raw)
                if isinstance(args, dict):
                    out.append((_strip_prefix(current_name), args))
            except (json.JSONDecodeError, TypeError):
                pass
        current_name = None
        collecting_args = False
        args_fragments = []

    for line in text.splitlines():
        if _BOX_CLOSE_RE.match(line):
            _flush()
            continue
        m = _TOOL_USE_RE.match(line)
        if m:
            _flush()
            current_name = m.group(1)
            continue
        if current_name is not None and not collecting_args:
            m = _ARGS_START_RE.match(line)
            if m:
                collecting_args = True
                args_fragments = [m.group(1)]
                continue
        if collecting_args:
            m = _ARGS_CONT_RE.match(line)
            if m:
                args_fragments.append(m.group(1))
            else:
                _flush()

    _flush()
    return out


def extract_trail(trace_path: Path, max_bullets: int = 8) -> list[str]:
    """Return up to `max_bullets` friendly bullets from a trace file.

    Deduplicates consecutive duplicates. Returns [] on missing/bad file.
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
            continue
        bullets.append(described)
        if len(bullets) >= max_bullets:
            break
    return bullets


def extract_trail_for_finding(
    trace_path: Path,
    finding: "Finding",  # type: ignore[name-defined]  # noqa: F821
    max_bullets: int = 6,
) -> list[str]:
    """Trail bullets attributed to a specific Finding (file-attribution heuristic).

    Always includes the first build_review_context bullet (universal context).
    Remaining bullets included iff they mention finding.file or its basename.
    Returns at most `max_bullets` in trace order.
    """
    all_bullets = extract_trail(trace_path, max_bullets=64)
    if not all_bullets:
        return []

    file_full = (finding.file or "").lower()
    file_base = Path(finding.file).name.lower() if finding.file else ""

    result: list[str] = []
    for i, bullet in enumerate(all_bullets):
        if len(result) >= max_bullets:
            break
        b_lower = bullet.lower()
        if i == 0 and "loaded the pr diff" in b_lower:
            result.append(bullet)
        elif file_full and file_full in b_lower:
            result.append(bullet)
        elif file_base and file_base in b_lower:
            result.append(bullet)

    return result
