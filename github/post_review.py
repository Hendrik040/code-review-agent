"""GitHub write-side: classify findings, render, POST one PR Review.

This module owns:
- _classify        : partition findings into inline vs orphan based on hunks
- render_payload_for_inspection : build the payload dict (used by inspect/dry-run)
- submit_review    : the actual HTTP POST to GitHub (Task 9)

Auth: GITHUB_REVIEW_BOT_TOKEN env var (Working-Ant identity). The token
is passed to submit_review explicitly — never read from os.environ here,
so tests can inject a fake without monkey-patching the environment.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.findings import Finding
from github.pr_fetch import Hunk


@dataclass(frozen=True)
class RunMeta:
    run_id: int
    sdk: str           # "agent" | "client"
    effort: str        # "high" | "xhigh" | ...
    timestamp_utc: str # ISO-8601 UTC, e.g. "2026-05-03T14:32:00Z"
    num_turns: int
    cost_usd: float


@dataclass(frozen=True)
class InlineComment:
    """One inline review comment, ready to be POSTed.

    Single-line: start_line is None.
    Multi-line:  start_line is set, line is the end line, both side="RIGHT".
    """
    path: str
    line: int
    side: str             # "RIGHT"
    body: str
    start_line: int | None = None
    start_side: str | None = None  # set to "RIGHT" iff start_line is set


def _span(f: Finding) -> tuple[int, int]:
    """Defensively-corrected (start_line, end_line) for a Finding."""
    end = f.line_end or f.line
    if end < f.line:
        return end, f.line  # swap reversed bounds
    return f.line, end


def _fits_in_one_hunk(span: tuple[int, int], hunks: list[Hunk]) -> bool:
    start, end = span
    for h in hunks:
        if h.start_line <= start and end <= h.end_line:
            return True
    return False


def _classify(
    findings: list[Finding],
    hunks: dict[str, list[Hunk]],
) -> tuple[list[InlineComment], list[Finding]]:
    """Partition findings into (inline, orphan).

    A finding is inline iff its full (line .. line_end) span fits inside
    a single hunk on side="RIGHT". Otherwise it's an orphan.
    """
    from github.review_body import render_inline_comment  # late import to avoid cycle

    inlines: list[InlineComment] = []
    orphans: list[Finding] = []

    for f in findings:
        file_hunks = hunks.get(f.file)
        if not file_hunks:
            orphans.append(f)
            continue
        start, end = _span(f)
        if not _fits_in_one_hunk((start, end), file_hunks):
            orphans.append(f)
            continue
        body = render_inline_comment(f)
        if start == end:
            inlines.append(InlineComment(
                path=f.file, line=start, side="RIGHT", body=body,
            ))
        else:
            inlines.append(InlineComment(
                path=f.file, line=end, side="RIGHT",
                start_line=start, start_side="RIGHT",
                body=body,
            ))

    return inlines, orphans
