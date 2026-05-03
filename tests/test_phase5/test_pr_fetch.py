"""Unit tests for github.pr_fetch — URL parsing + dataclasses (Task 1)."""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from github.pr_fetch import PullRequest, Hunk, _parse_pr_url


class TestParsePrUrl:
    def test_https_basic(self):
        assert _parse_pr_url("https://github.com/Hendrik040/sentry/pull/1") == (
            "Hendrik040", "sentry", 1
        )

    def test_https_with_trailing_slash(self):
        assert _parse_pr_url("https://github.com/owner/repo/pull/42/") == (
            "owner", "repo", 42
        )

    def test_http_is_accepted(self):
        assert _parse_pr_url("http://github.com/o/r/pull/7") == ("o", "r", 7)

    def test_rejects_non_pull_url(self):
        with pytest.raises(ValueError, match="not a GitHub PR URL"):
            _parse_pr_url("https://github.com/owner/repo/issues/1")

    def test_rejects_non_github_host(self):
        with pytest.raises(ValueError, match="not a GitHub PR URL"):
            _parse_pr_url("https://gitlab.com/owner/repo/pull/1")

    def test_rejects_garbage(self):
        with pytest.raises(ValueError, match="not a GitHub PR URL"):
            _parse_pr_url("not a url")

    def test_rejects_url_with_query_string(self):
        # Browser-paste URLs often include ?tab=commits or #discussion_r1
        with pytest.raises(ValueError, match="not a GitHub PR URL"):
            _parse_pr_url("https://github.com/owner/repo/pull/1?tab=commits")


class TestDataclasses:
    def test_pullrequest_is_frozen(self):
        pr = PullRequest(
            owner="o", repo="r", number=1,
            base_sha="a", head_sha="b",
            title="t", html_url="u",
        )
        with pytest.raises(FrozenInstanceError):
            pr.owner = "x"  # frozen dataclass

    def test_hunk_is_frozen(self):
        h = Hunk(start_line=1, end_line=10, side="RIGHT")
        with pytest.raises(FrozenInstanceError):
            h.start_line = 99
