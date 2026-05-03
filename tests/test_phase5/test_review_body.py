"""Snapshot tests for github.review_body — tightened render_inline_comment."""

from __future__ import annotations

from shared.findings import Finding
from github.review_body import render_inline_comment, SEVERITY_BADGES


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
