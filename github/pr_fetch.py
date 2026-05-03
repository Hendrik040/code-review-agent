"""Read-side GitHub: PR metadata + diff hunks via the `gh` CLI.

Used by scripts/github/review_pr.py and the inspect_* helpers. Wraps
`gh api` calls (no token in process; auth is via the user's `gh auth`
state). Write-side posting lives in github/post_review.py and uses a
separate token (GITHUB_REVIEW_BOT_TOKEN).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# https://github.com/<owner>/<repo>/pull/<n>(/)
_PR_URL_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$"
)


@dataclass(frozen=True)
class PullRequest:
    owner: str
    repo: str
    number: int
    base_sha: str
    head_sha: str
    title: str
    html_url: str


@dataclass(frozen=True)
class Hunk:
    """An added-line range in a PR file's diff. side is always 'RIGHT'
    for v1 — we only comment on new code, never on the deleted side."""
    start_line: int
    end_line: int
    side: Literal["RIGHT"]


def _parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    m = _PR_URL_RE.match(pr_url.strip())
    if not m:
        raise ValueError(
            f"not a GitHub PR URL: {pr_url!r} "
            "(expected https://github.com/<owner>/<repo>/pull/<n>)"
        )
    owner, repo, number = m.group(1), m.group(2), int(m.group(3))
    return owner, repo, number


# Hunk header: @@ -<old_start>[,<old_count>] +<new_start>[,<new_count>] @@
# We only care about the +<new_start>,<new_count> portion (the RIGHT side).
_HUNK_HEADER_RE = re.compile(
    r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@"
)


def _parse_patch_to_hunks(patch: str) -> list[Hunk]:
    """Extract added-line ranges from a unified-diff patch string.

    Returns one Hunk per `@@ ... @@` header that has a non-zero new-side
    count. Zero-count headers (pure deletions) are omitted — there's
    nothing on the RIGHT side to comment on.
    """
    hunks: list[Hunk] = []
    for line in patch.splitlines():
        m = _HUNK_HEADER_RE.match(line)
        if not m:
            continue
        new_start = int(m.group(1))
        new_count = int(m.group(2)) if m.group(2) is not None else 1
        if new_count == 0:
            continue  # pure deletion, nothing to anchor a comment to
        hunks.append(Hunk(new_start, new_start + new_count - 1, "RIGHT"))
    return hunks
