"""Render individual Findings as GitHub-friendly inline-comment Markdown.

Single public entry point:
- render_inline_comment(finding, analysis_trail=()) -> str
    The body of one inline review comment. Tightened template: bold
    summary headline (a fix-recommendation, not a noun-phrase bug name),
    inline file:line + severity badge, 2-3 sentence detail paragraph,
    collapsible "Prompt for AI agents" block.

Summary-level rendering (run header, orphans, analysis trail) lives in
github/review_summary.py which imports SEVERITY_BADGES and _location
from this module.

The PLAN.md "no emoji" rule applies to source code; rendered output to
GitHub uses badges/icons because they read well in-PR (confirmed during
brainstorming).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Union

from shared.findings import Finding

if TYPE_CHECKING:
    from github.trace_extract import TrailExtract

SEVERITY_BADGES: dict[str, str] = {
    "high": "🟥 High risk",
    "medium": "🔶 Medium risk",
    "low": "🔹 Low risk",
}


def _location(f: Finding) -> str:
    """Render the file:line(-line_end) anchor for a Finding.

    Returns "file:L" for single-line findings, "file:L-E" for ranges.
    Caller is responsible for ensuring line_end >= line if set —
    post_review._classify (Task 8) defensively swaps reversed bounds
    before findings reach this layer.
    """
    if f.line_end and f.line_end != f.line:
        return f"{f.file}:{f.line}-{f.line_end}"
    return f"{f.file}:{f.line}"


def render_inline_comment(
    finding: Finding,
    *,
    analysis_trail: "Union[Iterable[str], TrailExtract, None]" = (),
) -> str:
    """Render one Finding as inline-comment markdown.

    `analysis_trail` may be a plain iterable of bullet strings (legacy) or a
    TrailExtract (new). When non-empty, a collapsible "Analysis trail" details
    block is inserted after the detail paragraph and before the AI agents block.
    """
    # Normalise: accept TrailExtract or plain iterable
    from github.trace_extract import TrailExtract
    if isinstance(analysis_trail, TrailExtract):
        trail_bullets = analysis_trail.bullets
        tool_summary = analysis_trail.tool_summary
    else:
        trail_bullets = list(analysis_trail or [])
        tool_summary = ""

    loc = _location(finding)
    sev = SEVERITY_BADGES.get(finding.severity, finding.severity.title())

    lines = [
        f"**{finding.summary}**",
        "",
        f"`{loc}` · {sev}",
        "",
        finding.detail,
        "",
    ]

    if trail_bullets:
        lines += [
            "<details>",
            f"<summary>🔎 Analysis trail ({len(trail_bullets)} steps)</summary>",
            "",
        ]
        if tool_summary:
            lines += [tool_summary, ""]
        for bullet in trail_bullets:
            lines.append(f"- {bullet}")
        lines += ["", "</details>", ""]

    fix_goal = (
        finding.suggested_fix.strip()
        or "Fix the bug while preserving the intended behavior."
    )
    lines += [
        "<details>",
        "<summary>🤖 Prompt for AI agents</summary>",
        "",
        # 4-backtick fence so finding text containing ``` doesn't break Markdown.
        "````text",
        "Verify this finding against the current code before editing.",
        "",
        f"Location: {loc}",
        f"Category: {finding.category}",
        f"Severity: {finding.severity}",
        "",
        "Finding:",
        finding.summary,
        "",
        "Context:",
        finding.detail,
        "",
        "Goal:",
        fix_goal,
        "",
        "Before finishing:",
        f"- Inspect {loc} directly.",
        "- Confirm the relevant caller/callee contracts involved in the finding.",
        "- Add or update a focused test that would fail before the fix.",
        "````",
        "",
        "</details>",
    ]
    return "\n".join(lines) + "\n"

