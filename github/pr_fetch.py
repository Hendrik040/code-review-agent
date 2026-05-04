"""Read-side GitHub: PR metadata + diff hunks via the `gh` CLI.

Used by scripts/github/review_pr.py and the inspect_* helpers. Wraps
`gh api` calls (no token in process; auth is via the user's `gh auth`
state). Write-side posting lives in github/post_review.py and uses a
separate token (GITHUB_REVIEW_BOT_TOKEN).
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Literal

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


# Hard cap on `gh api` calls so a stalled auth/network handshake can't
# deadlock the one-shot review workflow. Sized for the largest PR-files
# pagination we expect (Sentry-class repos, low hundreds of files).
_GH_API_TIMEOUT_SECONDS = 60


def _gh_json(endpoint: str) -> Any:
    """Invoke `gh api <endpoint>` and parse stdout as JSON."""
    out = subprocess.check_output(
        ["gh", "api", endpoint],
        text=True, timeout=_GH_API_TIMEOUT_SECONDS,
    )
    return json.loads(out)


def _gh_json_paginated(endpoint: str) -> list[Any]:
    """Invoke `gh api --paginate --slurp <endpoint>` and flatten the
    list-of-pages response into a single list. Plain `_gh_json` returns
    only the first page (~30 items by default); large PRs lose files
    silently without paginate."""
    out = subprocess.check_output(
        ["gh", "api", "--paginate", "--slurp", endpoint],
        text=True, timeout=_GH_API_TIMEOUT_SECONDS,
    )
    pages = json.loads(out)
    flat: list[Any] = []
    for page in pages:
        flat.extend(page)
    return flat


def fetch_pr(pr_url: str) -> PullRequest:
    """Parse the PR URL and fetch metadata via `gh api`."""
    owner, repo, number = _parse_pr_url(pr_url)
    data = _gh_json(f"repos/{owner}/{repo}/pulls/{number}")
    return PullRequest(
        owner=owner,
        repo=repo,
        number=number,
        base_sha=data["base"]["sha"],
        head_sha=data["head"]["sha"],
        title=data["title"],
        html_url=data["html_url"],
    )


def fetch_diff_hunks(
    owner: str, repo: str, pr_number: int
) -> dict[str, list[Hunk]]:
    """Fetch the PR's changed-file list and parse each file's patch into
    Hunk ranges. Files with no RIGHT-side content (pure deletions, binary
    files without a patch) are omitted from the result."""
    files = _gh_json_paginated(f"repos/{owner}/{repo}/pulls/{pr_number}/files")
    out: dict[str, list[Hunk]] = {}
    for entry in files:
        patch = entry.get("patch") or ""
        hunks = _parse_patch_to_hunks(patch)
        if hunks:
            out[entry["filename"]] = hunks
    return out


@dataclass(frozen=True)
class Comment:
    """A PR review comment anchored to a file + line range."""
    comment_id: int
    file_path: str
    line_start: int       # 1-indexed; equals line_end for single-line
    line_end: int
    body: str
    author: str
    created_at: str       # ISO-8601


def list_open_prs(owner_repo: str, *, since: str | None = None) -> list[PullRequest]:
    """List open PRs in `owner/repo`. Optional `since` is ISO-8601;
    PRs with `updated_at < since` are filtered out client-side."""
    raw = _gh_json_paginated(f"repos/{owner_repo}/pulls?state=open&per_page=100")
    owner, repo = owner_repo.split("/", 1)
    out: list[PullRequest] = []
    for item in raw:
        if since and item.get("updated_at", "") < since:
            continue
        out.append(PullRequest(
            owner=owner, repo=repo, number=int(item["number"]),
            base_sha=item["base"]["sha"], head_sha=item["head"]["sha"],
            title=item["title"], html_url=item["html_url"],
        ))
    return out


def list_pr_review_comments(pr: PullRequest, *, since_id: int | None = None) -> list[Comment]:
    """List review comments on a PR. Optional `since_id` filters out
    comment ids ≤ since_id (matches our cursor semantics).

    Skips comments where GitHub's `line` is null — those are outdated
    review threads (the anchored line was rewritten away) or file-level
    comments. Phase 6's downstream chunker needs a real line number;
    a `Comment(line_start=0, line_end=0)` would silently return garbage
    AST chunks. Drop here at the source.
    """
    raw = _gh_json_paginated(
        f"repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/comments?per_page=100"
    )
    out: list[Comment] = []
    for item in raw:
        cid = int(item["id"])
        if since_id is not None and cid <= since_id:
            continue
        if item.get("line") is None:
            continue  # outdated thread or file-level comment — skip
        line = int(item["line"])
        start = int(item.get("start_line") or line)
        out.append(Comment(
            comment_id=cid,
            file_path=item.get("path", ""),
            line_start=start,
            line_end=line,
            body=item.get("body", ""),
            author=(item.get("user") or {}).get("login", ""),
            created_at=item.get("created_at", ""),
        ))
    return out
