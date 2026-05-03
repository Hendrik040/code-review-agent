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

import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from shared.findings import Finding
from github.pr_fetch import PullRequest, Hunk
from github.review_summary import render_review_summary


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


_GITHUB_API = "https://api.github.com"
_HTTP_TIMEOUT_SECONDS = 30


def _to_inline_payload(c: InlineComment) -> dict:
    """Convert an InlineComment dataclass to the GH REST API shape."""
    payload: dict = {
        "path": c.path,
        "line": c.line,
        "side": c.side,
        "body": c.body,
    }
    if c.start_line is not None:
        payload["start_line"] = c.start_line
        payload["start_side"] = c.start_side or "RIGHT"
    return payload


def render_payload_for_inspection(
    pr: PullRequest,
    findings: list[Finding],
    hunks: dict[str, list[Hunk]],
    run_meta: RunMeta,
    trail: list[str],
    *,
    repo_path: Path | None = None,
    truncated: bool = False,
) -> dict:
    """Build the full POST payload without sending it. Used by --dry-run
    and inspect_render.py."""
    inlines, orphans = _classify(findings, hunks)
    summary = render_review_summary(
        run_meta, orphans, trail, repo_path=repo_path, truncated=truncated,
    )
    return {
        "commit_id": pr.head_sha,
        "event": "COMMENT",
        "body": summary,
        "comments": [_to_inline_payload(c) for c in inlines],
    }


def submit_review(
    pr: PullRequest,
    findings: list[Finding],
    hunks: dict[str, list[Hunk]],
    run_meta: RunMeta,
    trail: list[str],
    token: str,
    *,
    repo_path: Path | None = None,
    truncated: bool = False,
) -> str:
    """POST a single PR Review with N inline comments + summary body.

    Returns the review's html_url on success. Raises RuntimeError with
    the GH response body on any non-2xx status — caller is responsible
    for the "saved to ..." retry-instruction message per spec section 7.

    Retries once on 5xx after a 5-second sleep (transient GH outage).
    """
    payload = render_payload_for_inspection(
        pr, findings, hunks, run_meta, trail,
        repo_path=repo_path, truncated=truncated,
    )
    url = f"{_GITHUB_API}/repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/reviews"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    for attempt in (1, 2):
        # httpx raises on transport failures (timeouts, conn refused,
        # DNS) instead of returning a response. Fold those into the
        # same retry-once-then-RuntimeError path so review_pr.py's
        # `except RuntimeError` catches them.
        try:
            resp = httpx.post(
                url, json=payload, headers=headers, timeout=_HTTP_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            if attempt == 1:
                time.sleep(5)
                continue
            raise RuntimeError(f"GitHub POST transport error: {exc!r}") from exc
        if 200 <= resp.status_code < 300:
            return resp.json()["html_url"]
        # Retry once on 5xx; raise immediately on 4xx (caller's bug)
        if 500 <= resp.status_code < 600 and attempt == 1:
            time.sleep(5)
            continue
        raise RuntimeError(
            f"GitHub POST failed with status {resp.status_code}: {resp.text}"
        )
    raise RuntimeError("unreachable")  # for type checker
