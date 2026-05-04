"""Unit tests for shared/learnings_prompt.py.

Regression coverage for the Task-9 review findings:
- github.com host-match must be boundary-aware (no false positives on
  notgithub.com / github.com.evil.example).
- fail-open paths must log via the module logger.
- (search_learnings credential sanitation is tested in test_reviewer
  integration, not here.)
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from shared.learnings_prompt import (
    infer_repo_slug,
    parse_changed_lines,
)


def _fake_repo(remote_url: str, *, raises: Exception | None = None) -> MagicMock:
    repo = MagicMock()
    if raises is not None:
        repo.exec.side_effect = raises
    else:
        result = MagicMock()
        result.stdout = remote_url
        repo.exec.return_value = result
    return repo


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/owner/repo", "owner/repo"),
        ("https://github.com/owner/repo.git", "owner/repo"),
        ("git@github.com:owner/repo", "owner/repo"),
        ("git@github.com:owner/repo.git", "owner/repo"),
        ("https://github.com/owner/repo/extra/path.git", "owner/repo"),
    ],
)
def test_infer_repo_slug_canonical_github_forms(url, expected):
    assert infer_repo_slug(_fake_repo(url)) == expected


@pytest.mark.parametrize(
    "url",
    [
        "git@notgithub.com:owner/repo.git",          # adversarial host
        "https://notgithub.com/owner/repo",          # adversarial host
        "https://github.com.evil.example/o/r",       # subdomain trick
        "https://gitlab.com/owner/repo",             # other forge
        "git@bitbucket.org:owner/repo.git",          # other forge
        "https://github.foo.com/owner/repo",         # GH Enterprise (out of scope v1)
        "",                                          # empty
        "not-a-url",                                 # garbage
    ],
)
def test_infer_repo_slug_rejects_non_github_or_lookalikes(url):
    assert infer_repo_slug(_fake_repo(url)) is None


def test_infer_repo_slug_returns_none_on_repo_exec_failure():
    repo = _fake_repo("", raises=RuntimeError("git not found"))
    assert infer_repo_slug(repo) is None


def test_parse_changed_lines_basic():
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -10,3 +10,4 @@\n"
        " ctx\n"
        "-old\n"
        "+new1\n"
        "+new2\n"
        " ctx\n"
    )
    assert parse_changed_lines(diff) == {"foo.py": [11, 12]}


def test_parse_changed_lines_skips_files_with_only_deletions():
    diff = (
        "diff --git a/x.py b/x.py\n"
        "--- a/x.py\n"
        "+++ b/x.py\n"
        "@@ -1,2 +1 @@\n"
        " kept\n"
        "-removed\n"
    )
    # No '+' lines -> file dropped from output.
    assert parse_changed_lines(diff) == {}


def test_parse_changed_lines_handles_multiple_files():
    diff = (
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1 +1,2 @@\n"
        " ctx\n"
        "+new_a\n"
        "diff --git a/b.py b/b.py\n"
        "--- a/b.py\n"
        "+++ b/b.py\n"
        "@@ -5 +5,2 @@\n"
        " ctx\n"
        "+new_b\n"
    )
    out = parse_changed_lines(diff)
    assert set(out.keys()) == {"a.py", "b.py"}
    assert out["a.py"] == [2]
    assert out["b.py"] == [6]


def test_build_user_prompt_with_learnings_logs_on_failure(caplog):
    """Spec §8.2: fail-open paths must log so operators can grep them."""
    from shared.learnings_prompt import build_user_prompt_with_learnings

    # Force the inner branch by giving a repo with .path so we exercise
    # the try/except, but rig the inner repo.exec to blow up.
    bad_repo = MagicMock()
    bad_repo.path = "/tmp/whatever"
    bad_repo.exec.side_effect = RuntimeError("git diff blew up")

    with caplog.at_level(logging.WARNING, logger="learnings.prompt"):
        out = build_user_prompt_with_learnings(
            repo=bad_repo, base_ref="HEAD~1", head_ref="HEAD",
            repo_slug="owner/repo",
        )
    # Reviewer keeps running with plain prompt.
    assert "<past_learnings>" not in out
    # The fail-open was logged.
    assert any("prompt-build skipped" in r.message for r in caplog.records)
