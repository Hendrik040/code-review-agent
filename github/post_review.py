"""GitHub write-side: classify findings, render, POST one PR Review.

Public API:
- _classify, render_payload_for_inspection, submit_review

Auth: GITHUB_REVIEW_BOT_TOKEN passed in explicitly — never read from os.environ.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import httpx

from shared.findings import Finding
from github.pr_fetch import PullRequest, Hunk
from github.review_summary import render_review_summary
from github.trace_extract import TrailExtract


@dataclass(frozen=True)
class RunMeta:
    run_id: int
    sdk: str
    effort: str
    timestamp_utc: str
    num_turns: int
    cost_usd: float


@dataclass(frozen=True)
class InlineComment:
    """One inline review comment, ready to be POSTed."""
    path: str
    line: int
    side: str
    body: str
    start_line: int | None = None
    start_side: str | None = None


def _span(f: Finding) -> tuple[int, int]:
    end = f.line_end or f.line
    return (end, f.line) if end < f.line else (f.line, end)


def _fits_in_one_hunk(span: tuple[int, int], hunks: list[Hunk]) -> bool:
    start, end = span
    return any(h.start_line <= start and end <= h.end_line for h in hunks)


def _classify(
    findings: list[Finding],
    hunks: dict[str, list[Hunk]],
    *,
    trace_path: Path | None = None,
) -> tuple[list[InlineComment], list[Finding]]:
    """Partition findings into (inline, orphan).

    A finding is inline iff its full span fits inside a single hunk on
    side="RIGHT". When trace_path is given, each inline comment gets its
    per-finding analysis trail.
    """
    from github.review_body import render_inline_comment
    from github.trace_extract import extract_trail_for_finding

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
        trail: Union[TrailExtract, tuple] = (
            extract_trail_for_finding(trace_path, f)
            if trace_path is not None else ()
        )
        body = render_inline_comment(f, analysis_trail=trail)
        if start == end:
            inlines.append(InlineComment(path=f.file, line=start, side="RIGHT", body=body))
        else:
            inlines.append(InlineComment(
                path=f.file, line=end, side="RIGHT",
                start_line=start, start_side="RIGHT", body=body,
            ))

    return inlines, orphans


_GITHUB_API = "https://api.github.com"
_HTTP_TIMEOUT_SECONDS = 30


def _to_inline_payload(c: InlineComment) -> dict:
    payload: dict = {"path": c.path, "line": c.line, "side": c.side, "body": c.body}
    if c.start_line is not None:
        payload["start_line"] = c.start_line
        payload["start_side"] = c.start_side or "RIGHT"
    return payload


def render_payload_for_inspection(
    pr: PullRequest,
    findings: list[Finding],
    hunks: dict[str, list[Hunk]],
    run_meta: RunMeta,
    trail: "Union[list[str], TrailExtract]",
    *,
    repo_path: Path | None = None,
    truncated: bool = False,
    trace_path: Path | None = None,
) -> dict:
    """Build the full POST payload without sending it."""
    inlines, orphans = _classify(findings, hunks, trace_path=trace_path)
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
    trail: "Union[list[str], TrailExtract]",
    token: str,
    *,
    repo_path: Path | None = None,
    truncated: bool = False,
    trace_path: Path | None = None,
) -> str:
    """POST a PR Review; return html_url. Retries once on 5xx. Never retries 4xx."""
    payload = render_payload_for_inspection(
        pr, findings, hunks, run_meta, trail,
        repo_path=repo_path, truncated=truncated, trace_path=trace_path,
    )
    url = f"{_GITHUB_API}/repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/reviews"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # POST /reviews is non-idempotent: a transport error after the
    # request reached GitHub but before we got the response would mean
    # a retry could create a DUPLICATE review. So we retry only on a
    # confirmed 5xx (server received + replied) and surface transport
    # errors immediately.
    for attempt in (1, 2):
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=_HTTP_TIMEOUT_SECONDS)
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"GitHub POST transport error (not retried to avoid duplicate reviews): {exc!r}"
            ) from exc
        if 200 <= resp.status_code < 300:
            return resp.json()["html_url"]
        if 500 <= resp.status_code < 600 and attempt == 1:
            time.sleep(5)
            continue
        raise RuntimeError(f"GitHub POST failed with status {resp.status_code}: {resp.text}")
    raise RuntimeError("unreachable")
