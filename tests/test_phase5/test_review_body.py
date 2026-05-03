"""Snapshot tests for github.review_body — tightened render_inline_comment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from shared.findings import Finding
from github.review_body import render_inline_comment, render_review_summary, SEVERITY_BADGES


@dataclass(frozen=True)
class _RunMetaStub:
    run_id: int
    sdk: str
    effort: str
    timestamp_utc: str
    num_turns: int
    cost_usd: float


def _meta(**overrides):
    base = dict(
        run_id=42, sdk="agent", effort="xhigh",
        timestamp_utc="2026-05-03T14:32:00Z",
        num_turns=19, cost_usd=1.30,
    )
    base.update(overrides)
    return _RunMetaStub(**base)


def test_render_inline_comment_tightened_template():
    f = Finding(
        file="src/sentry/incidents/grouptype.py",
        line=11,
        line_end=12,
        category="contract-mismatch",
        severity="medium",
        summary=(
            "Implement the abstract methods or keep MetricAlertDetectorHandler "
            "on the non-stateful base for now."
        ),
        detail=(
            "StatefulDetectorHandler declares four abstract methods "
            "(counter_names, get_dedupe_value, get_group_key_values, "
            "build_occurrence_and_event_data). Detector.detector_handler "
            "instantiates the subclass at detector.py:86, which now raises "
            "TypeError. Either implement the four methods or revert to the "
            "non-stateful parent class."
        ),
        suggested_fix="",
    )
    out = render_inline_comment(f)

    # Bold summary leads
    assert out.startswith("**Implement the abstract methods")
    # File anchor + severity badge inline (one line, two tokens)
    assert "`src/sentry/incidents/grouptype.py:11-12`" in out
    assert SEVERITY_BADGES["medium"] in out
    # The DROPPED elements must not appear
    assert "Review note" not in out, (
        "old 'Review note | severity' header should be gone"
    )
    # The detail paragraph is present
    assert "StatefulDetectorHandler declares four abstract methods" in out
    # "Prompt for AI agents" collapsible block is present
    assert "<summary>" in out and "Prompt for AI agents" in out


def test_render_inline_comment_single_line_location():
    # When line_end is None or equals line, location renders as `file:line`
    f = Finding(
        file="a.py", line=5, line_end=None,
        category="logic", severity="low",
        summary="Use .get() instead of [].",
        detail="x. y. z.",
        suggested_fix="",
    )
    out = render_inline_comment(f)
    assert "`a.py:5`" in out
    assert "`a.py:5-" not in out


def test_render_inline_comment_severity_badges_used():
    # All three severities must have a badge
    for sev in ("high", "medium", "low"):
        assert sev in SEVERITY_BADGES or sev.title() in str(SEVERITY_BADGES)


def test_render_inline_comment_keeps_analysis_trail_param():
    # Backward-compat: the param stays in the signature, but v1 callers
    # pass () because the trail moved to the wrapping review's summary.
    # Verify the param is INERT — passing a non-empty trail produces the
    # same output as passing none. If a future change accidentally starts
    # consuming the trail here, this test catches it.
    f = Finding(
        file="a.py", line=1, line_end=None,
        category="other", severity="low",
        summary="x", detail="y", suggested_fix="",
    )
    out_empty = render_inline_comment(f, analysis_trail=())
    out_with = render_inline_comment(f, analysis_trail=("step 1", "step 2"))
    assert out_empty == out_with, (
        "analysis_trail must be inert in v1 — same output regardless of value"
    )


def test_run_header_line_is_present():
    out = render_review_summary(_meta(), orphans=[], trail=[], repo_path=None)
    assert "**Run #042**" in out
    assert "Agent SDK" in out
    assert "effort=xhigh" in out
    assert "19 turns" in out
    assert "$1.30" in out
    # Timestamp rendered as friendly format, not raw ISO
    assert "2026-05-03 14:32 UTC" in out


def test_no_orphans_no_caution_block():
    out = render_review_summary(_meta(), orphans=[], trail=[], repo_path=None)
    assert "[!CAUTION]" not in out
    assert "Outside diff range" not in out


def test_orphans_render_caution_block_with_snippet(tmp_path: Path):
    # Set up a fake cloned repo containing the file the orphan references
    src = tmp_path / "src" / "x.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "line 1\nline 2\nline 3\nORPHAN LINE 4\nline 5\nline 6\nline 7\n"
    )
    orphan = Finding(
        file="src/x.py", line=4, line_end=None,
        category="logic", severity="medium",
        summary="Recommendation here.",
        detail="Detail here.",
        suggested_fix="",
    )
    out = render_review_summary(
        _meta(), orphans=[orphan], trail=[], repo_path=tmp_path,
    )
    assert "[!CAUTION]" in out
    assert "Outside diff range comments (1)" in out
    assert "src/x.py:4" in out
    assert "Recommendation here." in out
    # Snippet is a fenced code block containing the orphan line plus context
    assert "```" in out
    assert "ORPHAN LINE 4" in out
    assert "line 2" in out  # +/- 2 lines of context
    assert "line 6" in out


def test_trail_renders_in_collapsible_details():
    out = render_review_summary(
        _meta(), orphans=[],
        trail=["Loaded the PR diff", "Read foo.py (lines 1-10)"],
        repo_path=None,
    )
    assert "Analysis trail" in out
    assert "<details>" in out
    assert "Loaded the PR diff" in out
    assert "Read foo.py (lines 1-10)" in out


def test_no_trail_no_trail_section():
    out = render_review_summary(_meta(), orphans=[], trail=[], repo_path=None)
    assert "Analysis trail" not in out


def test_truncated_renders_warning_header():
    out = render_review_summary(
        _meta(), orphans=[], trail=[], repo_path=None, truncated=True,
    )
    assert "[!WARNING]" in out
    assert "MAX_TURNS" in out
    assert "Run #042" in out


def test_not_truncated_no_warning():
    out = render_review_summary(_meta(), orphans=[], trail=[], repo_path=None)
    assert "[!WARNING]" not in out
