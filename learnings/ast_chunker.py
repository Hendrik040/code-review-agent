"""AST-based chunker for Phase 6.

Uses ``ast-grep`` (already required by the project; see
``shared/agent_tools.py:59``) to find function and class-method boundaries.
The same chunker runs at capture-time (single anchor → enclosing unit) and
query-time (diff → all changed enclosing units; see Task 7).

Python-only for v1. Multi-language requires per-language patterns.
"""
from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

# ast-grep patterns. $$$ matches any sequence; $NAME matches an identifier.
# We pull functions, async functions, and classes.
#
# NOTE: The plan originally specified patterns ending in ``: $$$`` (e.g.
# ``def $NAME($$$): $$$``). Those return zero matches in ast-grep 0.42.1
# because ast-grep matches whole tree-sitter nodes — the pattern
# ``def $NAME($$$)`` already binds to the entire ``function_definition``
# node (header + body) and the trailing ``: $$$`` confuses the parser.
# Verified by hand on the fixtures before tweaking. The captured node's
# ``range`` already covers the full body, which is what we need.
_PY_FUNC_PATTERN = "def $NAME($$$)"
_PY_ASYNC_FUNC_PATTERN = "async def $NAME($$$)"
_PY_CLASS_PATTERN = "class $NAME"

_AST_TIMEOUT_S = 15.0
_FALLBACK_WINDOW = 50  # lines on each side when no AST unit fits


@dataclass(frozen=True)
class Chunk:
    text: str
    kind: str                 # "function" | "method" | "module-scope" | "fallback_window"
    line_start: int           # 1-indexed, inclusive
    line_end: int             # 1-indexed, inclusive


@dataclass(frozen=True)
class _AstNode:
    text: str
    line_start: int
    line_end: int
    kind: str                 # "function" or "class"
    parent_class_line_start: int | None  # for "method" detection


def _run_ast_grep(file: Path, pattern: str) -> list[dict]:
    cmd = (
        f"ast-grep run -p {shlex.quote(pattern)} "
        f"--lang python --json=stream {shlex.quote(str(file))}"
    )
    proc = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=_AST_TIMEOUT_S
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"ast-grep failed: {proc.stderr}")
    out: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _collect_nodes(file: Path) -> list[_AstNode]:
    """Find every function, async function, and class. Mark methods
    (functions whose enclosing parent is a class) at output time."""
    src = file.read_text()
    src_lines = src.splitlines()
    classes = _run_ast_grep(file, _PY_CLASS_PATTERN)
    funcs = _run_ast_grep(file, _PY_FUNC_PATTERN) + _run_ast_grep(file, _PY_ASYNC_FUNC_PATTERN)

    def _span(node: dict) -> tuple[int, int, str]:
        # ast-grep uses 0-indexed line numbers in `range.start.line`.
        s = node["range"]["start"]["line"] + 1
        e = node["range"]["end"]["line"] + 1
        text = "\n".join(src_lines[s - 1 : e])
        return s, e, text

    class_spans = [(*_span(c), "class") for c in classes]
    func_spans = [(*_span(f), "function") for f in funcs]

    def _find_parent_class(s: int) -> int | None:
        for cs, ce, _, _ in class_spans:
            if cs < s <= ce:
                return cs
        return None

    out: list[_AstNode] = []
    for s, e, text, _ in func_spans:
        out.append(
            _AstNode(
                text=text,
                line_start=s,
                line_end=e,
                kind="function",
                parent_class_line_start=_find_parent_class(s),
            )
        )
    for s, e, text, _ in class_spans:
        out.append(
            _AstNode(text=text, line_start=s, line_end=e, kind="class", parent_class_line_start=None)
        )
    return out


def chunk_for_anchor(file: Path, *, line_start: int, line_end: int) -> Chunk:
    """Find the smallest AST unit (function/method) fully containing
    [line_start, line_end]. Returns a fallback ±50-line window if no
    AST unit fits or if the range crosses unit boundaries.
    """
    if line_end < line_start:
        line_start, line_end = line_end, line_start

    try:
        nodes = _collect_nodes(file)
    except Exception:
        return _fallback_window(file, line_start, line_end)

    enclosing = [
        n for n in nodes
        if n.line_start <= line_start and line_end <= n.line_end and n.kind == "function"
    ]
    if not enclosing:
        return _fallback_window(file, line_start, line_end)

    # Smallest function that fully contains the range.
    n = min(enclosing, key=lambda x: x.line_end - x.line_start)
    kind = "method" if n.parent_class_line_start is not None else "function"
    return Chunk(text=n.text, kind=kind, line_start=n.line_start, line_end=n.line_end)


def _fallback_window(file: Path, line_start: int, line_end: int) -> Chunk:
    src_lines = file.read_text().splitlines()
    n = len(src_lines)
    s = max(1, line_start - _FALLBACK_WINDOW)
    e = min(n, line_end + _FALLBACK_WINDOW)
    text = "\n".join(src_lines[s - 1 : e])
    # If the original anchor lines are completely outside any function and
    # the file is small, "module-scope" is more accurate; otherwise call
    # it a fallback_window so the consumer can filter on `chunk_kind`.
    kind = "module-scope" if e - s + 1 == n else "fallback_window"
    return Chunk(text=text, kind=kind, line_start=s, line_end=e)
