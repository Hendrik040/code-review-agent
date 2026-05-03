"""AST chunker — function/method/module-scope extraction via ast-grep.

Capture-side: chunk_for_anchor(file, line_range) -> Chunk
Query-side:   chunks_for_diff(repo_path, changed) -> list[Chunk]
              (added in Task 7)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from learnings.ast_chunker import Chunk, chunk_for_anchor

FIXTURES = Path(__file__).parent / "fixtures"


def test_chunk_for_anchor_returns_enclosing_function():
    # tiny_module.py: first_function spans 5..7, second spans 10..13
    c = chunk_for_anchor(FIXTURES / "tiny_module.py", line_start=6, line_end=6)
    assert c.kind == "function"
    assert c.line_start == 5 and c.line_end == 7
    assert "def first_function" in c.text
    assert "second_function" not in c.text


def test_chunk_for_anchor_returns_enclosing_method():
    # nested_class.py: method_one is inside OuterClass
    c = chunk_for_anchor(FIXTURES / "nested_class.py", line_start=10, line_end=10)
    assert c.kind == "method"
    assert "def method_one" in c.text
    assert "def method_two" not in c.text


def test_chunk_for_anchor_falls_back_for_module_scope():
    # Anchor on the GLOBAL_CONST line (line 3) — ast-grep succeeds but
    # no function encloses → kind="module-scope" (NOT "fallback_window";
    # fallback_window is reserved for ast-grep failures).
    c = chunk_for_anchor(FIXTURES / "tiny_module.py", line_start=3, line_end=3)
    assert c.kind == "module-scope"
    assert "GLOBAL_CONST" in c.text


def test_chunk_for_anchor_picks_smallest_enclosing_unit():
    # nested_class.py: line inside method_two (lines 13..18) should
    # return the METHOD, not the enclosing class.
    c = chunk_for_anchor(FIXTURES / "nested_class.py", line_start=18, line_end=18)
    assert c.kind == "method"
    assert "def method_two" in c.text
    assert "def method_one" not in c.text


def test_chunk_for_anchor_expands_to_cover_full_range():
    # Multi-line range that crosses two functions — no single function
    # encloses the range, so ast-grep "succeeds with no enclosing match"
    # path fires → kind="module-scope".
    c = chunk_for_anchor(FIXTURES / "tiny_module.py", line_start=6, line_end=11)
    assert c.kind == "module-scope"


def test_chunk_for_anchor_uses_fallback_window_on_ast_failure(tmp_path):
    """ast-grep returncode ≠ (0,1) raises RuntimeError, which the
    chunker converts to kind='fallback_window' — distinct from
    'module-scope' which means ast-grep succeeded with no enclosing match."""
    from unittest.mock import patch
    src = tmp_path / "x.py"
    src.write_text("def foo():\n    return 1\n")
    with patch("learnings.ast_chunker._collect_nodes", side_effect=RuntimeError("simulated")):
        c = chunk_for_anchor(src, line_start=1, line_end=1)
    assert c.kind == "fallback_window"
    assert "def foo" in c.text


from learnings.ast_chunker import chunks_for_diff


def test_chunks_for_diff_returns_changed_function():
    # Hand-roll the changed-line map directly: one file, one changed line.
    repo_path = FIXTURES  # treat fixtures dir as repo root
    changed = {"tiny_module.py": [7]}
    chunks = chunks_for_diff(repo_path, changed)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.kind == "function"
    assert "first_function" in c.text


def test_chunks_for_diff_dedupes_within_one_function():
    # Multiple changed lines inside the same function -> one chunk.
    changed = {"tiny_module.py": [6, 7]}
    chunks = chunks_for_diff(FIXTURES, changed)
    assert len(chunks) == 1


def test_chunks_for_diff_skips_missing_files():
    chunks = chunks_for_diff(FIXTURES, {"does_not_exist.py": [1]})
    assert chunks == []


def test_chunks_for_diff_handles_module_scope_changes():
    # Line 3 (GLOBAL_CONST) — no enclosing function. Should still
    # produce a chunk via the fallback path.
    chunks = chunks_for_diff(FIXTURES, {"tiny_module.py": [3]})
    assert len(chunks) == 1
    # Task 5's split: ast-grep ran fine but no function encloses line 3,
    # so chunks_for_diff calls _fallback_window(kind="module-scope").
    # Assert exact kind so a regression to default ("fallback_window") fails.
    assert chunks[0].kind == "module-scope"
