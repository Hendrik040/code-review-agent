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

from datetime import datetime
from pathlib import Path
from typing import Iterable, Protocol

from shared.findings import Finding

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
        finding.suggested_fix.strip()
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


# ---------------------------------------------------------------------------
# render_review_summary — wrapping PR Review body (Task 7)
# ---------------------------------------------------------------------------


class _RunMetaLike(Protocol):
    """Structural type for the RunMeta object passed in.

    The real RunMeta lives in github/post_review.py (Task 9). Defining
    it here as a Protocol avoids a circular import while keeping the
    rendering layer typed.
    """
    run_id: int
    sdk: str
    effort: str
    timestamp_utc: str        # ISO-8601, e.g. "2026-05-03T14:32:00Z"
    num_turns: int
    cost_usd: float


_SNIPPET_CONTEXT = 2  # lines of context above + below the orphan


def _format_timestamp(iso: str) -> str:
    """Render '2026-05-03T14:32:00Z' as '2026-05-03 14:32 UTC' for display."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, AttributeError):
        return iso  # if format is unexpected, show raw rather than crash


def _render_run_header(meta: "_RunMetaLike") -> str:
    sdk_label = "Agent SDK" if meta.sdk == "agent" else "Client SDK"
    return (
        f"**Run #{meta.run_id:03d}** · {sdk_label} · "
        f"effort={meta.effort} · {_format_timestamp(meta.timestamp_utc)} · "
        f"{meta.num_turns} turns · ${meta.cost_usd:.2f}"
    )


def _read_snippet(repo_path: Path | None, file_path: str,
                  start: int, end: int) -> str | None:
    """Read +/- _SNIPPET_CONTEXT lines around [start..end] from the file.

    Returns None if the file can't be read — the orphan still renders,
    just without the snippet block.
    """
    if repo_path is None:
        return None
    full = Path(repo_path) / file_path
    try:
        all_lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
    except (FileNotFoundError, OSError):
        return None
    lo = max(1, start - _SNIPPET_CONTEXT)
    hi = min(len(all_lines), end + _SNIPPET_CONTEXT)
    if lo > hi:
        return None
    # 1-indexed slice
    return "\n".join(all_lines[lo - 1:hi])


def _render_orphan(orphan: Finding, repo_path: Path | None) -> str:
    loc = _location(orphan)
    sev = SEVERITY_BADGES.get(orphan.severity, orphan.severity.title())
    end = orphan.line_end or orphan.line
    snippet = _read_snippet(repo_path, orphan.file, orphan.line, end)
    parts = [
        f"#### `{loc}` · {sev}",
        "",
        f"**{orphan.summary}**",
        "",
        orphan.detail,
        "",
    ]
    if snippet is not None:
        parts += [
            "```",
            snippet,
            "```",
            "",
        ]
    return "\n".join(parts)


def render_review_summary(
    meta: "_RunMetaLike",
    orphans: list[Finding],
    trail: list[str],
    *,
    repo_path: Path | None = None,
    truncated: bool = False,
) -> str:
    """Render the body of the wrapping PR Review.

    `repo_path` is the local cloned repo (RepoState.path) — used to read
    snippets for orphan findings. Pass None if you don't have it on
    hand (orphans render without snippets).

    `truncated=True` means the reviewer hit max_turns without calling
    submit_findings — render a warning header so demo viewers know
    findings may be incomplete.
    """
    sections: list[str] = [_render_run_header(meta), ""]

    if truncated:
        sections += [
            "> [!WARNING]",
            f"> Run #{meta.run_id:03d} hit MAX_TURNS without calling "
            "submit_findings. Findings below may be incomplete.",
            "",
        ]

    if orphans:
        sections += [
            "> [!CAUTION]",
            "> Some comments are outside the diff and can't be posted "
            "inline due to platform limits.",
            "",
            "<details>",
            f"<summary>🔭 Outside diff range comments ({len(orphans)})</summary>",
            "",
            *[_render_orphan(o, repo_path) for o in orphans],
            "</details>",
            "",
        ]

    if trail:
        sections += [
            "<details>",
            f"<summary>🔎 Analysis trail ({len(trail)} steps)</summary>",
            "",
            *[f"- {bullet}" for bullet in trail],
            "",
            "</details>",
            "",
        ]

    return "\n".join(sections).rstrip() + "\n"
