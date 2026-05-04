"""Capture pipeline — one iteration is the unit. --watch loops it."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from github.pr_fetch import Comment, PullRequest
from learnings.capture import capture_once


def _pr(number: int = 1) -> PullRequest:
    return PullRequest(
        owner="o", repo="r", number=number, base_sha="b", head_sha="h",
        title="t", html_url=f"https://github.com/o/r/pull/{number}",
    )


def _comment(cid: int, body: str = "@Working-Ant learn always X",
             file_path: str = "tiny_module.py", line: int = 6) -> Comment:
    return Comment(
        comment_id=cid, file_path=file_path,
        line_start=line, line_end=line, body=body,
        author="alice", created_at="2026-05-03T10:00:00Z",
    )


def test_capture_once_skips_when_no_mention(tmp_path):
    adapter = MagicMock()
    adapter.list_open_prs.return_value = [_pr()]
    adapter.list_pr_review_comments.return_value = [_comment(1, body="LGTM")]
    embedder = MagicMock()
    store = MagicMock()
    with patch("learnings.capture.chunk_for_anchor") as ck:
        capture_once(
            repo="o/r", adapter=adapter, embedder=embedder, store=store,
            state_path=tmp_path / "state.json", repo_clone_root=tmp_path,
            handle="@Working-Ant", call_words=("learn",),
        )
    embedder.embed_one.assert_not_called()
    store.upsert.assert_not_called()
    ck.assert_not_called()


def test_capture_once_processes_mention_end_to_end(tmp_path):
    adapter = MagicMock()
    adapter.list_open_prs.return_value = [_pr()]
    adapter.list_pr_review_comments.return_value = [_comment(1)]
    embedder = MagicMock()
    embedder.embed_one.return_value = [0.1] * 1024
    store = MagicMock()

    # Materialize a real source file the chunker will read.
    src = tmp_path / "tiny_module.py"
    src.write_text("def first_function(x):\n    return x + 1\n")

    with patch("learnings.capture._ensure_clone", return_value=tmp_path):
        capture_once(
            repo="o/r", adapter=adapter, embedder=embedder, store=store,
            state_path=tmp_path / "state.json", repo_clone_root=tmp_path,
            handle="@Working-Ant", call_words=("learn",),
        )
    embedder.embed_one.assert_called_once()
    store.upsert.assert_called_once()
    args, kwargs = store.upsert.call_args
    payload = kwargs["payload"]
    assert payload.learning_text == "always X"
    assert payload.repo == "o/r"
    assert payload.author == "alice"


def test_capture_once_advances_cursor_after_success(tmp_path):
    state_path = tmp_path / "state.json"
    adapter = MagicMock()
    adapter.list_open_prs.return_value = [_pr()]
    adapter.list_pr_review_comments.return_value = [_comment(42)]
    embedder = MagicMock(); embedder.embed_one.return_value = [0.1] * 1024
    store = MagicMock()

    src = tmp_path / "tiny_module.py"
    src.write_text("def first_function(x):\n    return x + 1\n")

    with patch("learnings.capture._ensure_clone", return_value=tmp_path):
        capture_once(
            repo="o/r", adapter=adapter, embedder=embedder, store=store,
            state_path=state_path, repo_clone_root=tmp_path,
            handle="@Working-Ant", call_words=("learn",),
        )
    import json
    assert json.loads(state_path.read_text())["o/r"] == 42


def test_capture_once_fails_open_on_per_comment_error(tmp_path):
    """A bad comment must not abort the whole iteration."""
    adapter = MagicMock()
    adapter.list_open_prs.return_value = [_pr()]
    adapter.list_pr_review_comments.return_value = [
        _comment(1, file_path="missing.py", line=999),  # bad anchor
        _comment(2, file_path="tiny_module.py", line=1),  # good anchor
    ]
    embedder = MagicMock(); embedder.embed_one.return_value = [0.1] * 1024
    store = MagicMock()

    src = tmp_path / "tiny_module.py"
    src.write_text("def first_function(x):\n    return x + 1\n")

    with patch("learnings.capture._ensure_clone", return_value=tmp_path):
        capture_once(
            repo="o/r", adapter=adapter, embedder=embedder, store=store,
            state_path=tmp_path / "state.json", repo_clone_root=tmp_path,
            handle="@Working-Ant", call_words=("learn",),
        )
    # Both comments processed — store called once for the good one.
    assert store.upsert.call_count == 1


from learnings.voyage_client import VoyageError


def test_capture_once_does_not_advance_on_voyage_error(tmp_path):
    """Spec §8.1 — VoyageError after retry-exhaustion is transient infra,
    not a per-comment problem. Cursor stays put so next iteration retries."""
    state_path = tmp_path / "state.json"
    adapter = MagicMock()
    adapter.list_open_prs.return_value = [_pr()]
    adapter.list_pr_review_comments.return_value = [_comment(42)]
    embedder = MagicMock()
    embedder.embed_one.side_effect = VoyageError("voyage 503 after retries")
    store = MagicMock()

    src = tmp_path / "tiny_module.py"
    src.write_text("def first_function(x):\n    return x + 1\n")

    with patch("learnings.capture._ensure_clone", return_value=tmp_path):
        capture_once(
            repo="o/r", adapter=adapter, embedder=embedder, store=store,
            state_path=state_path, repo_clone_root=tmp_path,
            handle="@Working-Ant", call_words=("learn",),
        )
    # Cursor was NOT advanced — file shouldn't exist (no successful upserts
    # ever, so State never persisted) OR if it does, the cursor isn't 42.
    if state_path.exists():
        import json
        assert json.loads(state_path.read_text()).get("o/r") != 42
    store.upsert.assert_not_called()


def test_capture_once_advances_on_anchor_failure(tmp_path):
    """Anchor problems (FileNotFoundError → permanent) MUST advance cursor
    so we don't retry forever on a comment whose source file is gone."""
    state_path = tmp_path / "state.json"
    adapter = MagicMock()
    adapter.list_open_prs.return_value = [_pr()]
    # Comment points at a file that never existed in the clone.
    adapter.list_pr_review_comments.return_value = [
        _comment(7, file_path="this_file_does_not_exist.py", line=1),
    ]
    embedder = MagicMock()
    store = MagicMock()

    with patch("learnings.capture._ensure_clone", return_value=tmp_path):
        capture_once(
            repo="o/r", adapter=adapter, embedder=embedder, store=store,
            state_path=state_path, repo_clone_root=tmp_path,
            handle="@Working-Ant", call_words=("learn",),
        )
    import json
    assert json.loads(state_path.read_text())["o/r"] == 7
    store.upsert.assert_not_called()
