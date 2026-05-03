"""Unit tests for github.post_review._classify."""

from __future__ import annotations

import pytest

from shared.findings import Finding
from github.pr_fetch import Hunk
from github.post_review import _classify, InlineComment


def _f(file="a.py", line=5, line_end=None, summary="r", detail="d"):
    return Finding(
        file=file, line=line, line_end=line_end,
        category="logic", severity="low",
        summary=summary, detail=detail, suggested_fix="",
    )


class TestClassifyInDiff:
    def test_single_line_inside_hunk_is_inline(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        inlines, orphans = _classify([_f("a.py", line=5)], hunks)
        assert len(inlines) == 1 and len(orphans) == 0
        assert inlines[0].path == "a.py"
        assert inlines[0].line == 5

    def test_range_fully_inside_one_hunk_is_inline(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        inlines, _ = _classify([_f("a.py", line=3, line_end=7)], hunks)
        assert len(inlines) == 1
        assert inlines[0].start_line == 3
        assert inlines[0].line == 7

    def test_at_hunk_boundary_inclusive(self):
        # First and last line of a hunk both qualify
        hunks = {"a.py": [Hunk(5, 10, "RIGHT")]}
        inlines, orphans = _classify(
            [_f("a.py", line=5), _f("a.py", line=10)], hunks
        )
        assert len(inlines) == 2 and len(orphans) == 0


class TestClassifyOrphans:
    def test_file_not_in_hunks_is_orphan(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        # b.py isn't a changed file
        inlines, orphans = _classify([_f("b.py", line=5)], hunks)
        assert len(inlines) == 0 and len(orphans) == 1

    def test_line_outside_all_hunks_is_orphan(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        inlines, orphans = _classify([_f("a.py", line=99)], hunks)
        assert len(inlines) == 0 and len(orphans) == 1

    def test_range_crossing_hunk_boundary_is_orphan(self):
        # Spans hunk boundary: GH would 422 on a partial-hunk inline
        hunks = {"a.py": [Hunk(1, 10, "RIGHT"), Hunk(20, 30, "RIGHT")]}
        inlines, orphans = _classify(
            [_f("a.py", line=5, line_end=25)], hunks
        )
        assert len(inlines) == 0 and len(orphans) == 1

    def test_range_spanning_two_separate_hunks_is_orphan(self):
        # Even though both endpoints are in *some* hunk, they're in
        # different hunks. Orphan it.
        hunks = {"a.py": [Hunk(1, 5, "RIGHT"), Hunk(10, 15, "RIGHT")]}
        inlines, orphans = _classify(
            [_f("a.py", line=3, line_end=12)], hunks
        )
        assert len(inlines) == 0 and len(orphans) == 1


class TestClassifyDefensive:
    def test_reversed_bounds_swap_then_check(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        # line=8, line_end=3 (reversed) — defensively swap, then it's inside hunk
        inlines, orphans = _classify(
            [_f("a.py", line=8, line_end=3)], hunks
        )
        assert len(inlines) == 1 and len(orphans) == 0
        # The emitted inline comment uses the corrected (swapped) bounds
        assert inlines[0].start_line == 3
        assert inlines[0].line == 8

    def test_two_findings_at_same_location_both_post(self):
        # We don't dedup — that's the reviewer's responsibility, not ours
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        inlines, orphans = _classify(
            [_f("a.py", line=5, summary="A"),
             _f("a.py", line=5, summary="B")],
            hunks,
        )
        assert len(inlines) == 2

    def test_empty_findings_returns_empty(self):
        inlines, orphans = _classify([], {"a.py": [Hunk(1, 10, "RIGHT")]})
        assert inlines == [] and orphans == []


def test_classify_passes_per_finding_trail_when_trace_path_given(tmp_path):
    """When trace_path is provided, _classify enriches each inline comment
    body with the per-finding trail."""
    trace = tmp_path / "t.txt"
    trace.write_text(
        "│ tool_use: mcp__reviewer__build_review_context\n"
        "│   args: {}\n"
        "└─\n"
        "│ tool_use: mcp__reviewer__bash\n"
        "│   args: {\"command\": \"head -100 a.py\"}\n"
        "└─\n"
    )
    f = Finding(file="a.py", line=5, line_end=None,
                category="other", severity="low",
                summary="x", detail="y", suggested_fix="")
    hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
    inlines, _ = _classify([f], hunks, trace_path=trace)
    assert "Analysis trail" in inlines[0].body
    assert "a.py" in inlines[0].body
