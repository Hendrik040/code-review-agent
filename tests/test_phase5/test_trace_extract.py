"""Unit tests for github.trace_extract — trace parsing + friendly-name mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from github.trace_extract import _describe_tool_call, extract_trail

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TestDescribeToolCall:
    def test_build_review_context(self):
        assert _describe_tool_call("build_review_context", {}) == (
            "Loaded the PR diff and surrounding context"
        )

    def test_read_file_section(self):
        result = _describe_tool_call("read_file_section", {
            "path": "src/sentry/incidents/grouptype.py",
            "start_line": 1, "end_line": 40,
        })
        assert result == "Read src/sentry/incidents/grouptype.py (lines 1-40)"

    def test_ast_search(self):
        result = _describe_tool_call("ast_search", {
            "pattern": "class StatefulDetectorHandler",
        })
        assert result == (
            "Searched the codebase for the StatefulDetectorHandler class definition"
        )

    def test_ast_search_generic_pattern(self):
        # Pattern that doesn't match the "class X" shape: fall back to a
        # generic phrasing instead of inventing structure.
        result = _describe_tool_call("ast_search", {"pattern": "$X.foo($$$)"})
        assert result == "Searched the codebase using a structural pattern"

    def test_grep(self):
        result = _describe_tool_call("grep", {"pattern": "@abstractmethod"})
        assert result == "Looked for `@abstractmethod` in the codebase"

    def test_bash_git_diff(self):
        result = _describe_tool_call("bash", {"command": "git diff --stat"})
        assert result == "Inspected which files the PR changes"

    def test_bash_other(self):
        # Any other bash command: generic phrasing, never echo the command verbatim
        result = _describe_tool_call("bash", {"command": "rm -rf /"})
        assert result == "Ran a shell command on the working tree"

    def test_submit_findings_omitted(self):
        # Terminal call, not part of the investigation
        assert _describe_tool_call("submit_findings", {"findings": []}) is None

    def test_unknown_tool_omitted(self):
        # Defensive: never crash; just skip
        assert _describe_tool_call("totally_made_up", {}) is None


class TestExtractTrail:
    def test_extracts_friendly_bullets_from_sample_trace(self):
        trail = extract_trail(FIXTURE_DIR / "sample_trace.txt")
        assert len(trail) > 0
        # First substantive call should be build_review_context
        assert trail[0] == "Loaded the PR diff and surrounding context"
        # Internal tool names must NEVER appear in the rendered trail
        for bullet in trail:
            for forbidden in ("ast_search", "build_review_context",
                              "read_file_section", "submit_findings",
                              "ODIS"):
                assert forbidden not in bullet, (
                    f"internal name {forbidden!r} leaked into trail: {bullet!r}"
                )

    def test_dedupes_consecutive_duplicates(self):
        # The fixture has two identical read_file_section calls in a row;
        # they should collapse to one bullet.
        trail = extract_trail(FIXTURE_DIR / "sample_trace.txt")
        # No two consecutive bullets are identical
        for prev, nxt in zip(trail, trail[1:]):
            assert prev != nxt, f"duplicate consecutive bullet: {prev!r}"

    def test_caps_at_max_bullets(self):
        trail = extract_trail(FIXTURE_DIR / "sample_trace.txt", max_bullets=3)
        assert len(trail) <= 3

    def test_returns_empty_on_missing_file(self):
        # Defensive: must NEVER raise; the summary just omits the trail block
        assert extract_trail(Path("/nonexistent/trace.txt")) == []

    def test_returns_empty_on_unparseable_file(self, tmp_path):
        f = tmp_path / "garbage.txt"
        f.write_text("this is not a trace at all")
        assert extract_trail(f) == []
