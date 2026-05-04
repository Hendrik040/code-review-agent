"""Adapter wraps github/pr_fetch.py for the capture pipeline."""
from __future__ import annotations

from unittest.mock import patch

from github.pr_fetch import Comment, PullRequest
from learnings.github_adapter import GitHubAdapter


def test_adapter_delegates_list_open_prs():
    fake_prs = [PullRequest(owner="o", repo="r", number=1, base_sha="b",
                            head_sha="h", title="t", html_url="u")]
    with patch("learnings.github_adapter.list_open_prs", return_value=fake_prs) as m:
        a = GitHubAdapter()
        out = a.list_open_prs("o/r", since="2026-01-01T00:00:00Z")
        assert out == fake_prs
        m.assert_called_once_with("o/r", since="2026-01-01T00:00:00Z")


def test_adapter_delegates_list_pr_review_comments():
    pr = PullRequest(owner="o", repo="r", number=1, base_sha="b",
                     head_sha="h", title="t", html_url="u")
    fake = [Comment(comment_id=1, file_path="f", line_start=1, line_end=1,
                    body="b", author="a", created_at="t")]
    with patch("learnings.github_adapter.list_pr_review_comments", return_value=fake) as m:
        a = GitHubAdapter()
        out = a.list_pr_review_comments(pr, since_id=10)
        assert out == fake
        m.assert_called_once_with(pr, since_id=10)
