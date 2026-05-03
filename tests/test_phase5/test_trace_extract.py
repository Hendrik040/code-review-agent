"""Unit tests for github.trace_extract — trace parsing + diagnostic bullet mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from github.trace_extract import (
    TrailExtract,
    _describe_tool_call,
    extract_trail,
    extract_trail_for_finding,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TestDescribeToolCall:
    """_describe_tool_call now returns: `<full_tool_name>` — <target>"""

    def test_build_review_context(self):
        result = _describe_tool_call("build_review_context", {})
        assert result == "`build_review_context` — loaded the PR diff and surrounding context"

    def test_build_review_context_mcp_prefix(self):
        # When the raw name has the MCP prefix it must be preserved in bullet
        result = _describe_tool_call("mcp__reviewer__build_review_context", {})
        assert result == "`mcp__reviewer__build_review_context` — loaded the PR diff and surrounding context"

    def test_read_file_section(self):
        result = _describe_tool_call("mcp__reviewer__read_file_section", {
            "path": "src/sentry/incidents/grouptype.py",
            "start_line": 1, "end_line": 40,
        })
        assert result == "`mcp__reviewer__read_file_section` — src/sentry/incidents/grouptype.py:1-40"

    def test_bullet_target_for_read_file_section(self):
        # Explicitly validate the path:start-end format
        result = _describe_tool_call("mcp__reviewer__read_file_section", {
            "path": "backend/utils.py", "start_line": 186, "end_line": 240,
        })
        assert result is not None
        assert "backend/utils.py:186-240" in result

    def test_ast_search_class(self):
        result = _describe_tool_call("mcp__reviewer__ast_search", {
            "pattern": "class StatefulDetectorHandler",
        })
        assert result is not None
        assert "mcp__reviewer__ast_search" in result
        assert "StatefulDetectorHandler" in result
        assert "class definition" in result

    def test_ast_search_generic_pattern(self):
        result = _describe_tool_call("ast_search", {"pattern": "$X.foo($$$)"})
        assert result is not None
        assert "structural pattern" in result
        assert "$X.foo($$$)" in result

    def test_ast_search_def_pattern(self):
        result = _describe_tool_call("ast_search", {"pattern": "def my_func"})
        assert result is not None
        assert "def definition" in result
        assert "my_func" in result

    def test_grep(self):
        result = _describe_tool_call("grep", {"pattern": "@abstractmethod"})
        assert result is not None
        assert "pattern: `@abstractmethod`" in result

    def test_bash_git_diff(self):
        result = _describe_tool_call("bash", {"command": "git diff --stat"})
        assert result is not None
        assert "inspected which files the PR changes" in result

    def test_bash_other_shows_command(self):
        # Non-git-diff bash commands surface the command
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
        assert "session.txt" in result

    def test_bash_sanitizes_tmp_path(self):
        result = _describe_tool_call("bash", {
            "command": "head -100 /tmp/odis_context.md",
        })
        assert "/tmp/" not in result, f"tmp path leaked: {result!r}"
        assert "odis_context.md" in result

    def test_bash_keeps_relative_paths(self):
        result = _describe_tool_call("bash", {"command": "cat src/foo.py"})
        assert "src/foo.py" in result

    def test_bash_truncates_long_commands(self):
        long_cmd = "echo " + "x" * 200
        result = _describe_tool_call("bash", {"command": long_cmd})
        # Full bullet (including `bash` — prefix) should be reasonably short
        assert len(result) < 120
        assert "…" in result

    def test_submit_findings_omitted(self):
        assert _describe_tool_call("submit_findings", {"findings": []}) is None

    def test_mcp_submit_findings_omitted(self):
        assert _describe_tool_call("mcp__reviewer__submit_findings", {"findings": []}) is None

    def test_unknown_tool_omitted(self):
        assert _describe_tool_call("totally_made_up", {}) is None

    def test_case_insensitive_bash(self):
        # Real traces use capitalized built-in tool names: Bash, Grep, Read
        result = _describe_tool_call("Bash", {"command": "git diff --stat"})
        assert result is not None
        assert "inspected which files the PR changes" in result
        # Name preserved as-is
        assert "`Bash`" in result

    def test_case_insensitive_grep(self):
        result = _describe_tool_call("Grep", {"pattern": "@abstractmethod"})
        assert result is not None
        assert "`Grep`" in result
        assert "pattern: `@abstractmethod`" in result

    def test_case_insensitive_read(self):
        result = _describe_tool_call("Read", {"file_path": "src/foo.py"})
        assert result is not None
        assert "src/foo.py" in result
        assert "`Read`" in result

    def test_write_file(self):
        result = _describe_tool_call("write_file", {"path": "scratch/notes.md"})
        assert result is not None
        assert "scratch/notes.md" in result

    def test_bullet_includes_full_mcp_tool_name(self):
        # Full mcp__reviewer__* prefix must appear in the bullet text
        result = _describe_tool_call("mcp__reviewer__bash", {"command": "cat src/x.py"})
        assert result is not None
        assert "mcp__reviewer__bash" in result

    def test_glob(self):
        result = _describe_tool_call("glob", {"pattern": "**/*.py"})
        assert result is not None
        assert "**/*.py" in result


class TestExtractTrail:
    def test_returns_trail_extract(self):
        result = extract_trail(FIXTURE_DIR / "sample_trace.txt")
        assert isinstance(result, TrailExtract)

    def test_extracts_bullets_from_sample_trace(self):
        result = extract_trail(FIXTURE_DIR / "sample_trace.txt")
        assert len(result.bullets) > 0
        # First substantive call should be build_review_context
        assert "loaded the pr diff" in result.bullets[0].lower()
        # Full MCP name must appear in the bullet
        assert "mcp__reviewer__build_review_context" in result.bullets[0]

    def test_tool_summary_present(self):
        result = extract_trail(FIXTURE_DIR / "sample_trace.txt")
        assert result.tool_summary.startswith("**Tools used:**")
        assert "build_review_context" in result.tool_summary

    def test_tool_inventory_counts_correctly(self, tmp_path):
        # 1x build_review_context + 3x bash -> inventory shows both
        trace = tmp_path / "trace.txt"
        trace.write_text(
            "│ tool_use: mcp__reviewer__build_review_context\n"
            "│   args: {\"base_ref\": \"HEAD~1\", \"head_ref\": \"HEAD\"}\n"
            "└─\n"
            "│ tool_use: mcp__reviewer__bash\n"
            "│   args: {\"command\": \"cat src/a.py\"}\n"
            "└─\n"
            "│ tool_use: mcp__reviewer__bash\n"
            "│   args: {\"command\": \"cat src/b.py\"}\n"
            "└─\n"
            "│ tool_use: mcp__reviewer__bash\n"
            "│   args: {\"command\": \"cat src/c.py\"}\n"
            "└─\n"
        )
        result = extract_trail(trace)
        # bash appears 3x (sorted first by count), build_review_context 1x
        assert "3× bash" in result.tool_summary
        assert "1× build_review_context" in result.tool_summary
        # bash should come before build_review_context (higher count)
        assert result.tool_summary.index("3× bash") < result.tool_summary.index("1× build_review_context")
        assert "_(all via mcp__reviewer)_" in result.tool_summary

    def test_dedupes_consecutive_duplicates(self):
        result = extract_trail(FIXTURE_DIR / "sample_trace.txt")
        for prev, nxt in zip(result.bullets, result.bullets[1:]):
            assert prev != nxt, f"duplicate consecutive bullet: {prev!r}"

    def test_caps_at_max_bullets(self):
        result = extract_trail(FIXTURE_DIR / "sample_trace.txt", max_bullets=3)
        assert len(result.bullets) <= 3

    def test_returns_empty_on_missing_file(self):
        result = extract_trail(Path("/nonexistent/trace.txt"))
        assert isinstance(result, TrailExtract)
        assert result.bullets == []
        assert result.tool_summary == ""

    def test_returns_empty_on_unparseable_file(self, tmp_path):
        f = tmp_path / "garbage.txt"
        f.write_text("this is not a trace at all")
        result = extract_trail(f)
        assert result.bullets == []

    def test_bash_call_produces_bullet(self):
        result = extract_trail(FIXTURE_DIR / "sample_trace.txt", max_bullets=8)
        assert any(
            "inspected which files the pr changes" in b.lower()
            or "cat " in b.lower() or "`" in b
            for b in result.bullets
        ), f"Bash call should produce a bullet; got: {result.bullets}"

    def test_extract_trail_on_real_run_043(self):
        """Regression test for the 'all-bash-collapsed-to-1' bug."""
        trace = Path(__file__).resolve().parent.parent.parent / "agent_sdk" / "traces" / "run_043.txt"
        if not trace.exists():
            pytest.skip(f"run_043 trace not present at {trace}")
        result = extract_trail(trace)
        assert len(result.bullets) >= 4, (
            f"trail too sparse — expected >=4 bullets, got {len(result.bullets)}: {result.bullets}"
        )

    def test_all_mcp_suffix(self, tmp_path):
        # When all tools are mcp__reviewer__*, the suffix should be present
        trace = tmp_path / "trace.txt"
        trace.write_text(
            "│ tool_use: mcp__reviewer__build_review_context\n"
            "│   args: {}\n"
            "└─\n"
            "│ tool_use: mcp__reviewer__read_file_section\n"
            "│   args: {\"path\": \"x.py\", \"start_line\": 1, \"end_line\": 10}\n"
            "└─\n"
        )
        result = extract_trail(trace)
        assert "_(all via mcp__reviewer)_" in result.tool_summary

    def test_mixed_tools_no_all_mcp_suffix(self, tmp_path):
        # When harness tools (Bash) mix with MCP tools, no 'all via' suffix
        trace = tmp_path / "trace.txt"
        trace.write_text(
            "│ tool_use: mcp__reviewer__build_review_context\n"
            "│   args: {}\n"
            "└─\n"
            "│ tool_use: Bash\n"
            "│   args: {\"command\": \"cat src/a.py\"}\n"
            "└─\n"
        )
        result = extract_trail(trace)
        assert "_(all via mcp__reviewer)_" not in result.tool_summary


class TestExtractTrailForFinding:
    def test_returns_trail_extract(self):
        from shared.findings import Finding
        f = Finding(file="totally_unrelated.py", line=1,
                    category="other", severity="low",
                    summary="x", detail="y", suggested_fix="")
        result = extract_trail_for_finding(FIXTURE_DIR / "sample_trace.txt", f)
        assert isinstance(result, TrailExtract)

    def test_includes_build_review_context_universally(self):
        from shared.findings import Finding
        f = Finding(file="totally_unrelated.py", line=1,
                    category="other", severity="low",
                    summary="x", detail="y", suggested_fix="")
        result = extract_trail_for_finding(FIXTURE_DIR / "sample_trace.txt", f)
        assert any("loaded the pr diff" in b.lower() for b in result.bullets)

    def test_attributes_by_basename(self, tmp_path):
        trace = tmp_path / "fake_trace.txt"
        trace.write_text(
            "│ tool_use: mcp__reviewer__build_review_context\n"
            "│   args: {}\n"
            "└─\n"
            "│ tool_use: mcp__reviewer__bash\n"
            "│   args: {\"command\": \"head -100 src/sentry/app.py\"}\n"
            "└─\n"
            "│ tool_use: mcp__reviewer__bash\n"
            "│   args: {\"command\": \"head -100 unrelated/other.py\"}\n"
            "└─\n"
        )
        from shared.findings import Finding
        f = Finding(file="src/sentry/app.py", line=10,
                    category="other", severity="low",
                    summary="x", detail="y", suggested_fix="")
        result = extract_trail_for_finding(trace, f)
        assert any("app.py" in b for b in result.bullets)
        assert not any("other.py" in b for b in result.bullets), (
            f"unrelated bullet attributed: {result.bullets}"
        )

    def test_caps_at_max_bullets(self):
        from shared.findings import Finding
        f = Finding(file="x.py", line=1, category="other", severity="low",
                    summary="x", detail="y", suggested_fix="")
        result = extract_trail_for_finding(
            FIXTURE_DIR / "sample_trace.txt", f, max_bullets=2,
        )
        assert len(result.bullets) <= 2

    def test_tool_summary_reflects_filtered_bullets(self, tmp_path):
        # The tool_summary for a finding should count only the attributed bullets
        trace = tmp_path / "trace.txt"
        trace.write_text(
            "│ tool_use: mcp__reviewer__build_review_context\n"
            "│   args: {}\n"
            "└─\n"
            "│ tool_use: mcp__reviewer__read_file_section\n"
            "│   args: {\"path\": \"backend/utils.py\", \"start_line\": 1, \"end_line\": 10}\n"
            "└─\n"
            "│ tool_use: mcp__reviewer__read_file_section\n"
            "│   args: {\"path\": \"frontend/other.tsx\", \"start_line\": 1, \"end_line\": 10}\n"
            "└─\n"
        )
        from shared.findings import Finding
        f = Finding(file="backend/utils.py", line=5,
                    category="other", severity="low",
                    summary="x", detail="y", suggested_fix="")
        result = extract_trail_for_finding(trace, f)
        # Only build_review_context + the utils.py read should be attributed
        assert len(result.bullets) == 2
        # Inventory should show 1x build_review_context + 1x read_file_section
        assert "1× build_review_context" in result.tool_summary
        assert "1× read_file_section" in result.tool_summary
        # frontend/other.tsx bullet should NOT appear
        assert not any("other.tsx" in b for b in result.bullets)
