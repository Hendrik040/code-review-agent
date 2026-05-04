"""AST-based chunker for Phase 6.

Uses ``ast-grep`` (already required by the project; see
``shared/agent_tools.py:59``) to find function and class-method boundaries.
The same chunker runs at capture-time (single anchor → enclosing unit) and
query-time (diff → all changed enclosing units; see Task 7).

Python-only for v1. Multi-language requires per-language patterns.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

# ast-grep patterns. $$$ matches any sequence; $NAME matches an identifier.
# `def $NAME($$$)` catches both sync and async functions — tree-sitter
# Python represents them both as `function_definition` nodes, so the
# pattern matches both forms. Each captured node's range covers the
# entire definition (header + body) — there is no ":" or trailing
# `: $$$` in the pattern because that confuses ast-grep's matcher in
# 0.42.x and produces zero matches.
_PY_FUNC_PATTERN = "def $NAME($$$)"
_PY_CLASS_PATTERN = "class $NAME"

_AST_TIMEOUT_S = 15.0
_FALLBACK_WINDOW = 50  # lines on each side when no AST unit fits

log = logging.getLogger("learnings.ast_chunker")


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
    cmd = [
        "ast-grep", "run", "-p", pattern,
        "--lang", "python", "--json=stream", str(file),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=_AST_TIMEOUT_S
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
    funcs = _run_ast_grep(file, _PY_FUNC_PATTERN)

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
    [line_start, line_end].

    Returns:
      - kind="function" or "method" if a function/method encloses the range
      - kind="module-scope" if ast-grep succeeded but no function encloses
        the anchor (the anchor IS at module level — top-level statements,
        constants, etc.)
      - kind="fallback_window" if ast-grep itself failed (timeout, parse
        error, etc.) — we don't actually know where the anchor sits.
    """
    if line_end < line_start:
        line_start, line_end = line_end, line_start

    try:
        nodes = _collect_nodes(file)
    except Exception as exc:
        # Spec §8.1 — log + fall back, never block the pipeline.
        log.warning("ast chunker fell back: file=%s err=%s", file, exc)
        return _fallback_window(file, line_start, line_end, kind="fallback_window")

    enclosing = [
        n for n in nodes
        if n.line_start <= line_start and line_end <= n.line_end and n.kind == "function"
    ]
    if not enclosing:
        # ast-grep ran fine; the anchor really is at module scope.
        return _fallback_window(file, line_start, line_end, kind="module-scope")

    # Smallest function that fully contains the range.
    n = min(enclosing, key=lambda x: x.line_end - x.line_start)
    kind = "method" if n.parent_class_line_start is not None else "function"
    return Chunk(text=n.text, kind=kind, line_start=n.line_start, line_end=n.line_end)


def _fallback_window(
    file: Path, line_start: int, line_end: int, *, kind: str = "fallback_window"
) -> Chunk:
    """Build a ±50-line window around the anchor. Caller chooses `kind`
    to communicate WHY the fallback fired (see chunk_for_anchor docstring)."""
    src_lines = file.read_text().splitlines()
    n = len(src_lines)
    s = max(1, line_start - _FALLBACK_WINDOW)
    e = min(n, line_end + _FALLBACK_WINDOW)
    text = "\n".join(src_lines[s - 1 : e])
    return Chunk(text=text, kind=kind, line_start=s, line_end=e)


def chunks_for_diff(repo_path: Path, changed: dict[str, list[int]]) -> list[Chunk]:
    """Map {file: [changed_line_numbers]} → deduped enclosing AST units.

    Per-line semantics mirror chunk_for_anchor: function/method enclosing
    the line wins; otherwise module-scope fallback. Missing files and
    ast-grep failures are skipped silently (caller logs upstream).
    """
    out: list[Chunk] = []
    seen: set[tuple[str, int, int]] = set()
    for file_path, lines in changed.items():
        full_path = repo_path / file_path
        if not full_path.exists():
            continue
        try:
            nodes = _collect_nodes(full_path)
        except Exception as exc:
            log.warning("ast chunker skipped file=%s err=%s", full_path, exc)
            continue
        funcs = [n for n in nodes if n.kind == "function"]
        for line in lines:
            enclosing = [n for n in funcs if n.line_start <= line <= n.line_end]
            if enclosing:
                n = min(enclosing, key=lambda x: x.line_end - x.line_start)
                key = (file_path, n.line_start, n.line_end)
                if key in seen:
                    continue
                seen.add(key)
                kind = "method" if n.parent_class_line_start is not None else "function"
                out.append(Chunk(text=n.text, kind=kind, line_start=n.line_start, line_end=n.line_end))
            else:
                c = _fallback_window(full_path, line, line, kind="module-scope")
                key = (file_path, c.line_start, c.line_end)
                if key in seen:
                    continue
                seen.add(key)
                out.append(c)
    return out
