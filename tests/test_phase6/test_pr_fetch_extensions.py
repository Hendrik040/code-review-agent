"""Tests for the Phase-6 contributions to github/pr_fetch.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from github.pr_fetch import (
    Comment,
    PullRequest,
    list_open_prs,
    list_pr_review_comments,
)


def test_list_open_prs_returns_dataclasses():
    fake = [
        {
            "number": 1, "title": "T1",
            "html_url": "https://github.com/o/r/pull/1",
            "base": {"sha": "b1"}, "head": {"sha": "h1"},
            "updated_at": "2026-05-03T10:00:00Z",
        },
        {
            "number": 2, "title": "T2",
            "html_url": "https://github.com/o/r/pull/2",
            "base": {"sha": "b2"}, "head": {"sha": "h2"},
            "updated_at": "2026-05-03T11:00:00Z",
        },
    ]
    with patch("github.pr_fetch._gh_json_paginated", return_value=fake):
        prs = list_open_prs("o/r")
    assert len(prs) == 2
    assert prs[0].owner == "o" and prs[0].repo == "r" and prs[0].number == 1


def test_list_open_prs_filters_by_since():
    fake = [
        {"number": 1, "title": "old", "html_url": "https://github.com/o/r/pull/1",
         "base": {"sha": "b"}, "head": {"sha": "h"}, "updated_at": "2026-04-01T10:00:00Z"},
        {"number": 2, "title": "new", "html_url": "https://github.com/o/r/pull/2",
         "base": {"sha": "b"}, "head": {"sha": "h"}, "updated_at": "2026-05-03T10:00:00Z"},
    ]
    with patch("github.pr_fetch._gh_json_paginated", return_value=fake):
        prs = list_open_prs("o/r", since="2026-05-01T00:00:00Z")
    assert [p.number for p in prs] == [2]


def test_list_pr_review_comments_returns_dataclasses():
    fake = [
        {
            "id": 1234567, "path": "src/foo.py", "line": 42,
            "start_line": None, "body": "@Working-Ant learn x",
            "user": {"login": "alice"}, "created_at": "2026-05-03T10:00:00Z",
        },
        {
            "id": 1234568, "path": "src/bar.py", "line": 99,
            "start_line": 95, "body": "lgtm",
            "user": {"login": "bob"}, "created_at": "2026-05-03T11:00:00Z",
        },
    ]
    pr = PullRequest(owner="o", repo="r", number=1, base_sha="b", head_sha="h",
                     title="t", html_url="https://github.com/o/r/pull/1")
    with patch("github.pr_fetch._gh_json_paginated", return_value=fake):
        cs = list_pr_review_comments(pr)
    assert len(cs) == 2
    assert cs[0].comment_id == 1234567
    assert cs[0].file_path == "src/foo.py"
    assert cs[0].line_start == 42 and cs[0].line_end == 42
    assert cs[1].line_start == 95 and cs[1].line_end == 99


def test_list_pr_review_comments_filters_since_id():
    fake = [
        {"id": 100, "path": "a", "line": 1, "start_line": None, "body": "x",
         "user": {"login": "a"}, "created_at": "2026-05-03T09:00:00Z"},
        {"id": 200, "path": "b", "line": 2, "start_line": None, "body": "y",
         "user": {"login": "a"}, "created_at": "2026-05-03T10:00:00Z"},
    ]
    pr = PullRequest(owner="o", repo="r", number=1, base_sha="b", head_sha="h",
                     title="t", html_url="https://github.com/o/r/pull/1")
    with patch("github.pr_fetch._gh_json_paginated", return_value=fake):
        cs = list_pr_review_comments(pr, since_id=100)
    assert [c.comment_id for c in cs] == [200]


def test_list_pr_review_comments_skips_null_line_outdated_threads():
    """GitHub returns line=null for outdated review threads (anchored
    line was rewritten) and file-level comments. The downstream chunker
    needs a real line number; coercing to 0 would silently produce
    garbage AST chunks. Drop these at the source."""
    fake = [
        {"id": 1, "path": "a.py", "line": None, "start_line": None,
         "body": "@Working-Ant learn outdated", "user": {"login": "alice"},
         "created_at": "2026-05-03T10:00:00Z"},
        {"id": 2, "path": "b.py", "line": 42, "start_line": None,
         "body": "@Working-Ant learn current", "user": {"login": "alice"},
         "created_at": "2026-05-03T11:00:00Z"},
    ]
    pr = PullRequest(owner="o", repo="r", number=1, base_sha="b", head_sha="h",
                     title="t", html_url="https://github.com/o/r/pull/1")
    with patch("github.pr_fetch._gh_json_paginated", return_value=fake):
        cs = list_pr_review_comments(pr)
    # Outdated comment (id=1, line=null) is dropped; current one kept.
    assert [c.comment_id for c in cs] == [2]
    assert cs[0].line_start == 42 and cs[0].line_end == 42


def test_list_pr_review_comments_skips_left_side_comments():
    """Comments anchored on deleted lines (side="LEFT") have non-null
    `line` but the line number refers to the BASE side of the diff, not
    the HEAD checkout that downstream chunking reads. Skip at source."""
    fake = [
        {"id": 1, "path": "a.py", "line": 10, "side": "LEFT",
         "start_line": None, "body": "@Working-Ant learn old code thing",
         "user": {"login": "alice"}, "created_at": "2026-05-03T10:00:00Z"},
        {"id": 2, "path": "b.py", "line": 20, "side": "RIGHT",
         "start_line": None, "body": "@Working-Ant learn new code thing",
         "user": {"login": "alice"}, "created_at": "2026-05-03T11:00:00Z"},
    ]
    pr = PullRequest(owner="o", repo="r", number=1, base_sha="b", head_sha="h",
                     title="t", html_url="https://github.com/o/r/pull/1")
    with patch("github.pr_fetch._gh_json_paginated", return_value=fake):
        cs = list_pr_review_comments(pr)
    assert [c.comment_id for c in cs] == [2]


def test_list_pr_review_comments_populates_in_reply_to_id():
    fake = [
        {"id": 100, "path": "a.py", "line": 1, "start_line": None,
         "body": "@Working-Ant remember X", "user": {"login": "alice"},
         "created_at": "2026-05-04T10:00:00Z", "in_reply_to_id": 50},
        {"id": 200, "path": "a.py", "line": 2, "start_line": None,
         "body": "@Working-Ant learn Y", "user": {"login": "alice"},
         "created_at": "2026-05-04T11:00:00Z"},  # no in_reply_to_id
    ]
    pr = PullRequest(owner="o", repo="r", number=1, base_sha="b", head_sha="h",
                     title="t", html_url="u")
    with patch("github.pr_fetch._gh_json_paginated", return_value=fake):
        cs = list_pr_review_comments(pr)
    assert cs[0].in_reply_to_id == 50
    assert cs[1].in_reply_to_id is None


def test_fetch_review_comment_roundtrips_parent_body():
    from github.pr_fetch import fetch_review_comment
    fake = {
        "id": 50, "path": "a.py", "line": 5, "start_line": None,
        "body": "Bug analysis text from the bot.",
        "user": {"login": "Working-Ant"},
        "created_at": "2026-05-04T09:00:00Z",
        "in_reply_to_id": None,
    }
    with patch("github.pr_fetch._gh_json", return_value=fake):
        c = fetch_review_comment("o", "r", 50)
    assert c.comment_id == 50
    assert c.body == "Bug analysis text from the bot."
    assert c.author == "Working-Ant"
    assert c.in_reply_to_id is None
