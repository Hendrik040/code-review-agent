"""Render Findings as GitHub-friendly Markdown.

Two public entry points:
- render_inline_comment(finding, analysis_trail=()) -> str
    The body of one inline review comment. Tightened template: bold
    summary headline (a fix-recommendation, not a noun-phrase bug name),
    inline file:line + severity badge, 2-3 sentence detail paragraph,
    collapsible "Prompt for AI agents" block.

- render_review_summary(run_meta, orphans, trail) -> str
    The summary body of the wrapping PR Review. Run-header line,
    optional CodeRabbit-style "Outside diff range comments" block,
    consolidated "Analysis trail" details block. (Implemented in Task 7.)

The PLAN.md "no emoji" rule applies to source code; rendered output to
GitHub uses badges/icons because they read well in-PR (confirmed during
brainstorming).
"""

from __future__ import annotations

from typing import Iterable

from shared.findings import Finding

SEVERITY_BADGES: dict[str, str] = {
    "high": "🟥 High risk",
    "medium": "🔶 Medium risk",
    "low": "🔹 Low risk",
}


def _location(f: Finding) -> str:
    if f.line_end and f.line_end != f.line:
        return f"{f.file}:{f.line}-{f.line_end}"
    return f"{f.file}:{f.line}"


def render_inline_comment(
    finding: Finding,
    *,
    analysis_trail: Iterable[str] = (),
) -> str:
    """Render one Finding as inline-comment markdown.

    `analysis_trail` is accepted for backward compat; v1 callers pass ()
    because the trail moved to the wrapping review's summary.
    """
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

    # The "Prompt for AI agents" block — copyable handoff prompt that
    # downstream agents can paste directly into a fix session.
    fix_goal = (
        finding.suggested_fix
        or "Fix the bug while preserving the intended behavior."
    )
    lines += [
        "<details>",
        "<summary>🤖 Prompt for AI agents</summary>",
        "",
        "```text",
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
        "```",
        "",
        "</details>",
    ]
    return "\n".join(lines) + "\n"
