"""Phase-6-shaped facade over Phase 5's github/pr_fetch.py.

Wrapping keeps the capture pipeline's GitHub dependency narrow (one
interface) and gives us a single swap point for future changes — e.g.
Phase 4 / Daytona moving the clone path off the host.
"""
from __future__ import annotations

from github.pr_fetch import (
    Comment,
    PullRequest,
    list_open_prs,
    list_pr_review_comments,
)


class GitHubAdapter:
    """Thin synchronous facade — capture daemon's only GitHub seam."""

    def list_open_prs(self, owner_repo: str, *, since: str | None = None) -> list[PullRequest]:
        return list_open_prs(owner_repo, since=since)

    def list_pr_review_comments(
        self, pr: PullRequest, *, since_id: int | None = None
    ) -> list[Comment]:
        return list_pr_review_comments(pr, since_id=since_id)
