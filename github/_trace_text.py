"""Low-level text helpers shared by trace_extract.py.

Extracted to keep trace_extract.py under the 200-LOC budget when
extract_trail_for_finding was added (per-finding attribution heuristic).
"""

from __future__ import annotations

import re
from collections import Counter

# Matches internal absolute paths that should not leak into user-visible text.
ABS_PATH_RE = re.compile(
    r"(?:/Users/[^\s]*/|/tmp/(?:[^\s]*/)?|/(?:private/)?var/[^\s]*/)([^\s/]+)"
)

_MCP_PREFIX = "mcp__reviewer__"


def sanitize_bash_cmd(cmd: str, *, max_len: int = 80) -> str:
    """Replace internal absolute paths with <…>/basename; truncate to max_len."""
    sanitized = ABS_PATH_RE.sub(r"<…>/\1", cmd)
    return sanitized if len(sanitized) <= max_len else sanitized[:max_len - 1] + "…"


def strip_mcp_prefix(name: str) -> str:
    """Strip the mcp__reviewer__ prefix if present."""
    return name[len(_MCP_PREFIX):] if name.startswith(_MCP_PREFIX) else name


def target_for(tool_key: str, args: dict) -> str:
    """Return the short target description (the part after the em-dash) for a tool call.

    `tool_key` is the LOWERCASED stripped name (no mcp__ prefix).
    """
    if tool_key == "build_review_context":
        return "loaded the PR diff and surrounding context"

    if tool_key == "read_file_section":
        path = args.get("path", "<unknown>")
        return f"{path}:{args.get('start_line', '?')}-{args.get('end_line', '?')}"

    if tool_key == "read":
        path = args.get("file_path", args.get("path", "<unknown>"))
        offset = args.get("offset")
        limit = args.get("limit")
        if offset is not None and limit is not None:
            return f"{path}:{offset}-{offset + limit - 1}"
        return path

    if tool_key == "glob":
        return f"glob: `{args.get('pattern', '')}`"

    if tool_key == "ast_search":
        pattern = args.get("pattern", "")
        m = re.match(r"class\s+(\w+)", pattern)
        if m:
            return f"class definition: {m.group(1)}"
        m = re.match(r"def\s+(\w+)", pattern)
        if m:
            return f"def definition: {m.group(1)}"
        return f"structural pattern: `{pattern}`"

    if tool_key == "grep":
        return f"pattern: `{args.get('pattern', '')}`"

    if tool_key == "bash":
        cmd = (args.get("command") or "").strip()
        if cmd.startswith("git diff"):
            return "inspected which files the PR changes"
        return f"`{sanitize_bash_cmd(cmd)}`"

    if tool_key == "write_file":
        return args.get("path", "<unknown>")

    # Unknown tool — best-effort from first arg value
    if args:
        first_val = next(iter(args.values()), None)
        if isinstance(first_val, str):
            return first_val[:60]
    return ""


def build_tool_inventory(raw_names: list[str]) -> str:
    """Build the 'Tools used:' inventory line from a list of raw tool names.

    Format: '**Tools used:** 1× build_review_context, 2× read_file_section _(all via mcp__reviewer)_'
    - Counts use the SHORT name (prefix stripped).
    - Sorted descending by count, tie-break alphabetical.
    - _(all via mcp__reviewer)_ suffix when ALL names carry the prefix.
    Returns "" for an empty list.
    """
    if not raw_names:
        return ""

    counts: Counter[str] = Counter(strip_mcp_prefix(n) for n in raw_names)
    all_mcp = all(n.startswith(_MCP_PREFIX) for n in raw_names)

    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    parts = [f"{cnt}× {name}" for name, cnt in items]
    inventory = ", ".join(parts)

    suffix = " _(all via mcp__reviewer)_" if all_mcp else ""
    return f"**Tools used:** {inventory}{suffix}"
