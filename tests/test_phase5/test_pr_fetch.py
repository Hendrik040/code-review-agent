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


from github.pr_fetch import _parse_patch_to_hunks


class TestParsePatchToHunks:
    def test_single_hunk(self):
        # +Y,M means: starting at NEW line Y, M new lines are added/context
        patch = "@@ -10,3 +10,5 @@\n context\n+added 1\n+added 2\n context\n context"
        assert _parse_patch_to_hunks(patch) == [Hunk(10, 14, "RIGHT")]

    def test_multiple_hunks(self):
        patch = (
            "@@ -1,3 +1,3 @@\n unchanged\n unchanged\n unchanged\n"
            "@@ -100,2 +120,4 @@\n line\n+a\n+b\n line"
        )
        assert _parse_patch_to_hunks(patch) == [
            Hunk(1, 3, "RIGHT"),
            Hunk(120, 123, "RIGHT"),
        ]

    def test_pure_addition_at_start(self):
        # New file: -0,0 means no prior lines; +1,N means N added lines
        patch = "@@ -0,0 +1,3 @@\n+a\n+b\n+c"
        assert _parse_patch_to_hunks(patch) == [Hunk(1, 3, "RIGHT")]

    def test_omits_zero_length_added(self):
        # Pure deletion: +Y,0 means no added lines on the new side
        patch = "@@ -10,2 +10,0 @@\n-removed 1\n-removed 2"
        # Nothing to comment on RIGHT side — no hunks emitted.
        assert _parse_patch_to_hunks(patch) == []

    def test_empty_patch(self):
        assert _parse_patch_to_hunks("") == []

    def test_single_added_line_default_count(self):
        # @@ -X +Y @@ form (no comma, count defaults to 1)
        patch = "@@ -5 +5 @@\n unchanged"
        assert _parse_patch_to_hunks(patch) == [Hunk(5, 5, "RIGHT")]
