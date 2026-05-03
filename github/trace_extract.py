"""Convert an agent trace file into a diagnostic analysis trail.

Each bullet shows: `<full_qualified_tool_name>` — <target description>
A "Tools used:" inventory line is generated for the details block header.

Trace format: each tool call is a box with `│ tool_use: <name>` and
`│   args: {json}` lines; multi-line args continue on `│ ` lines;
box closes with `└─`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from github._trace_text import sanitize_bash_cmd, strip_mcp_prefix, target_for, build_tool_inventory  # noqa: F401

_TOOL_USE_RE = re.compile(r"^\│ tool_use: (\S+)\s*$")
_ARGS_START_RE = re.compile(r"^\│   args: (.+)$")
_ARGS_CONT_RE = re.compile(r"^\│ (.+)$")
_BOX_CLOSE_RE = re.compile(r"^└─")

_KNOWN_TOOLS = frozenset({
    "build_review_context", "read_file_section", "read", "glob",
    "ast_search", "grep", "bash", "write_file",
})


@dataclass(frozen=True)
class TrailExtract:
    """Structured result from extract_trail / extract_trail_for_finding."""
    tool_summary: str          # "**Tools used:** ..." line, or "" if empty
    bullets: list[str] = field(default_factory=list)


def _describe_tool_call(raw_name: str, args: dict) -> str | None:
    """Return a diagnostic bullet or None to omit this tool call.

    Format: `<full_qualified_tool_name>` — <target description>
    MCP tools keep the full mcp__reviewer__* wire name.
    Harness built-ins (Bash, Read, Grep, Glob) keep their capitalized names.
    Only known investigative tools are surfaced; meta-tools (ToolSearch,
    submit_findings) are omitted.
    """
    tool_key = strip_mcp_prefix(raw_name).lower()

    # Skip tools that are not part of the investigative surface
    if tool_key not in _KNOWN_TOOLS:
        return None

    target = target_for(tool_key, args)
    return f"`{raw_name}` — {target}"


def _parse_trace(text: str) -> list[tuple[str, dict]]:
    """Extract (raw_name, args_dict) tuples; robust to bad JSON. Never raises."""
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
                    out.append((current_name, args))
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


def _build_bullets(raw_calls: list[tuple[str, dict]], max_bullets: int) -> tuple[list[str], list[str]]:
    """Produce (bullets, included_raw_names) from parsed calls, capped at max_bullets.

    Deduplicates consecutive identical bullets.
    """
    bullets: list[str] = []
    raw_names: list[str] = []
    for raw_name, args in raw_calls:
        described = _describe_tool_call(raw_name, args)
        if described is None:
            continue
        if bullets and bullets[-1] == described:
            continue
        bullets.append(described)
        raw_names.append(raw_name)
        if len(bullets) >= max_bullets:
            break
    return bullets, raw_names


def extract_trail(trace_path: Path, max_bullets: int = 8) -> TrailExtract:
    """Return a TrailExtract with up to `max_bullets` diagnostic bullets.

    Deduplicates consecutive duplicates. Returns empty TrailExtract on missing/bad file.
    """
    try:
        text = Path(trace_path).read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return TrailExtract(tool_summary="", bullets=[])

    raw_calls = _parse_trace(text)
    bullets, raw_names = _build_bullets(raw_calls, max_bullets)
    return TrailExtract(tool_summary=build_tool_inventory(raw_names), bullets=bullets)


def extract_trail_for_finding(
    trace_path: Path,
    finding: "Finding",  # type: ignore[name-defined]  # noqa: F821
    max_bullets: int = 6,
) -> TrailExtract:
    """TrailExtract attributed to a specific Finding (file-attribution heuristic).

    Always includes the first build_review_context bullet (universal context).
    Remaining bullets included iff the bullet text mentions finding.file or its basename.
    Attribution is matched against the full bullet (which contains the target path).
    Returns at most `max_bullets` in trace order.
    """
    try:
        text = Path(trace_path).read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return TrailExtract(tool_summary="", bullets=[])

    raw_calls = _parse_trace(text)
    all_bullets, all_raw_names = _build_bullets(raw_calls, max_bullets=64)

    if not all_bullets:
        return TrailExtract(tool_summary="", bullets=[])

    file_full = (finding.file or "").lower()
    file_base = Path(finding.file).name.lower() if finding.file else ""

    result_bullets: list[str] = []
    result_raw: list[str] = []

    for i, (bullet, raw_name) in enumerate(zip(all_bullets, all_raw_names)):
        if len(result_bullets) >= max_bullets:
            break
        b_lower = bullet.lower()
        if i == 0 and "loaded the pr diff" in b_lower:
            result_bullets.append(bullet)
            result_raw.append(raw_name)
        elif file_full and file_full in b_lower:
            result_bullets.append(bullet)
            result_raw.append(raw_name)
        elif file_base and file_base in b_lower:
            result_bullets.append(bullet)
            result_raw.append(raw_name)

    return TrailExtract(tool_summary=build_tool_inventory(result_raw), bullets=result_bullets)
