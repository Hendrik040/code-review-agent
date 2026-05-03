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

    def test_bash_other_shows_command(self):
        # Non-git-diff bash commands surface the command (truncated, sanitized)
        result = _describe_tool_call("bash", {"command": "rm -rf /tmp/scratch"})
        assert result is not None
        assert "rm -rf" in result

    def test_bash_sanitizes_internal_user_path(self):
        # Internal Claude Code session paths must NOT leak into bullets
        result = _describe_tool_call("bash", {
            "command": "wc -l /Users/foo/.claude/projects/abc/session.txt",
        })
        assert "/Users/foo/.claude" not in result, (
            f"internal path leaked: {result!r}"
        )
        # The basename should be visible so the bullet still says something useful
        assert "session.txt" in result

    def test_bash_sanitizes_tmp_path(self):
        result = _describe_tool_call("bash", {
            "command": "head -100 /tmp/odis_context.md",
        })
        assert "/tmp/" not in result, f"tmp path leaked: {result!r}"
        assert "odis_context.md" in result

    def test_bash_keeps_relative_paths(self):
        # Relative paths are useful, keep them
        result = _describe_tool_call("bash", {"command": "cat src/foo.py"})
        assert "src/foo.py" in result

    def test_bash_truncates_long_commands(self):
        long_cmd = "echo " + "x" * 200
        result = _describe_tool_call("bash", {"command": long_cmd})
        # Bullet wrapping (Ran `...`) plus truncation. Cap is around 80 + a little.
        assert len(result) < 100
        assert "…" in result

    def test_submit_findings_omitted(self):
        # Terminal call, not part of the investigation
        assert _describe_tool_call("submit_findings", {"findings": []}) is None

    def test_unknown_tool_omitted(self):
        # Defensive: never crash; just skip
        assert _describe_tool_call("totally_made_up", {}) is None

    def test_case_insensitive_bash(self):
        # Real traces use capitalized built-in tool names: Bash, Grep, Read
        result = _describe_tool_call("Bash", {"command": "git diff --stat"})
        assert result == "Inspected which files the PR changes"

    def test_case_insensitive_grep(self):
        result = _describe_tool_call("Grep", {"pattern": "@abstractmethod"})
        assert result == "Looked for `@abstractmethod` in the codebase"

    def test_case_insensitive_read(self):
        # The harness built-in Read tool — uses file_path field name, not path
        result = _describe_tool_call("Read", {"file_path": "src/foo.py"})
        # Don't assert exact wording; just confirm a bullet is produced
        assert result is not None
        assert "src/foo.py" in result

    def test_ast_search_def_pattern(self):
        result = _describe_tool_call("ast_search", {"pattern": "def my_func"})
        assert result == "Searched the codebase for the my_func function definition"

    def test_write_file(self):
        result = _describe_tool_call("write_file", {"path": "scratch/notes.md"})
        assert result == "Wrote scratch notes to scratch/notes.md"


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

    def test_bash_call_produces_bullet(self):
        # Regression test: the original fixture used capitalized Bash but
        # the test never asserted a Bash-derived bullet appeared. Catch
        # the case-sensitivity bug going forward.
        trail = extract_trail(FIXTURE_DIR / "sample_trace.txt", max_bullets=8)
        assert any(
            "Inspected which files the PR changes" in b
            or "Ran `" in b
            for b in trail
        ), f"Bash call should produce a bullet; got: {trail}"

    def test_extract_trail_on_real_run_043(self):
        """Regression test for the 'all-bash-collapsed-to-1' bug.

        run_043.txt was the first real-world Phase 5 run (DIY-Finder PR);
        it exposed that 24 distinct bash commands collapsed to 1 bullet
        because they all rendered identically. After the fix, distinct
        bash commands render distinctly.
        """
        trace = Path(__file__).resolve().parent.parent.parent / "agent_sdk" / "traces" / "run_043.txt"
        if not trace.exists():
            pytest.skip(f"run_043 trace not present at {trace}")
        bullets = extract_trail(trace)
        # Should be more than the original 2-bullet collapse
        assert len(bullets) >= 4, (
            f"trail too sparse — expected >=4 bullets, got {len(bullets)}: {bullets}"
        )
