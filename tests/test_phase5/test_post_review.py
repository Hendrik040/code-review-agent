"""Unit tests for the HTTP layer of github.post_review."""

from __future__ import annotations

from unittest.mock import patch as mock_patch, MagicMock

import pytest

from shared.findings import Finding
from github.pr_fetch import PullRequest, Hunk
from github.post_review import (
    RunMeta, submit_review, render_payload_for_inspection,
)


def _pr():
    return PullRequest(
        owner="Hendrik040", repo="sentry", number=1,
        base_sha="abc123", head_sha="def456",
        title="t", html_url="https://github.com/Hendrik040/sentry/pull/1",
    )


def _meta():
    return RunMeta(
        run_id=42, sdk="agent", effort="xhigh",
        timestamp_utc="2026-05-03T14:32:00Z",
        num_turns=19, cost_usd=1.30,
    )


def _f(file="a.py", line=5, summary="r"):
    return Finding(
        file=file, line=line, line_end=None,
        category="logic", severity="low",
        summary=summary, detail="d.", suggested_fix="",
    )


class TestRenderPayloadForInspection:
    def test_payload_shape_with_inline_only(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        payload = render_payload_for_inspection(
            _pr(), [_f("a.py", line=5)], hunks, _meta(), trail=[],
        )
        assert payload["commit_id"] == "def456"
        assert payload["event"] == "COMMENT"
        assert "**Run #042**" in payload["body"]
        assert len(payload["comments"]) == 1
        assert payload["comments"][0]["path"] == "a.py"
        assert payload["comments"][0]["line"] == 5
        assert payload["comments"][0]["side"] == "RIGHT"
        assert "start_line" not in payload["comments"][0]  # single-line

    def test_orphan_lands_in_summary_not_comments(self):
        # b.py isn't in the hunks dict — orphan
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        payload = render_payload_for_inspection(
            _pr(), [_f("b.py", line=5)], hunks, _meta(), trail=[],
        )
        assert payload["comments"] == []
        assert "Outside diff range comments (1)" in payload["body"]


class TestSubmitReview:
    def test_posts_to_correct_endpoint_with_token(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {
            "html_url": "https://github.com/o/r/pull/1#pullrequestreview-555"
        }
        with mock_patch("github.post_review.httpx.post") as post:
            post.return_value = fake_resp
            url = submit_review(
                _pr(), [_f("a.py", line=5)], hunks, _meta(),
                trail=[], token="ghp_fake",
            )
        assert url == "https://github.com/o/r/pull/1#pullrequestreview-555"
        called_url = post.call_args[0][0]
        assert called_url == (
            "https://api.github.com/repos/Hendrik040/sentry/pulls/1/reviews"
        )
        headers = post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "token ghp_fake"
        assert headers["Accept"] == "application/vnd.github+json"

    def test_raises_on_4xx_no_retry(self):
        fake_resp = MagicMock(status_code=422)
        fake_resp.text = '{"message": "position outside diff"}'
        with mock_patch("github.post_review.httpx.post") as post:
            post.return_value = fake_resp
            with pytest.raises(RuntimeError, match="422"):
                submit_review(
                    _pr(), [_f("a.py", line=5)],
                    {"a.py": [Hunk(1, 10, "RIGHT")]},
                    _meta(), trail=[], token="ghp_fake",
                )
        # 4xx means caller bug (e.g. position outside diff) — never retry
        assert post.call_count == 1

    def test_retries_once_on_5xx_then_succeeds(self):
        first = MagicMock(status_code=503)
        first.text = "service unavailable"
        second = MagicMock(status_code=200)
        second.json.return_value = {"html_url": "https://x/y"}
        with mock_patch("github.post_review.httpx.post") as post, \
             mock_patch("github.post_review.time.sleep"):
            post.side_effect = [first, second]
            url = submit_review(
                _pr(), [_f("a.py", line=5)],
                {"a.py": [Hunk(1, 10, "RIGHT")]},
                _meta(), trail=[], token="ghp_fake",
            )
        assert url == "https://x/y"
        assert post.call_count == 2

    def test_raises_after_5xx_retry_also_fails(self):
        fake = MagicMock(status_code=503)
        fake.text = "still unavailable"
        with mock_patch("github.post_review.httpx.post") as post, \
             mock_patch("github.post_review.time.sleep"):
            post.return_value = fake
            with pytest.raises(RuntimeError, match="503"):
                submit_review(
                    _pr(), [_f("a.py", line=5)],
                    {"a.py": [Hunk(1, 10, "RIGHT")]},
                    _meta(), trail=[], token="ghp_fake",
                )
        assert post.call_count == 2
