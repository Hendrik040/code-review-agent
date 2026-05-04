"""Cursor file: tracks the highest-seen comment_id per repo."""
from __future__ import annotations

from pathlib import Path

from learnings.state import State


def test_advance_and_load_roundtrip(tmp_path: Path):
    p = tmp_path / "state.json"
    s = State(p)
    assert s.cursor("owner/repo") is None
    s.advance("owner/repo", 100)
    assert s.cursor("owner/repo") == 100

    # New instance reads from disk.
    s2 = State(p)
    assert s2.cursor("owner/repo") == 100


def test_advance_only_moves_forward(tmp_path: Path):
    s = State(tmp_path / "state.json")
    s.advance("owner/repo", 100)
    s.advance("owner/repo", 50)
    assert s.cursor("owner/repo") == 100  # never regress


def test_per_repo_isolation(tmp_path: Path):
    s = State(tmp_path / "state.json")
    s.advance("a/b", 1)
    s.advance("c/d", 99)
    assert s.cursor("a/b") == 1
    assert s.cursor("c/d") == 99


def test_corrupt_file_is_treated_as_empty(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text("not json {{{")
    s = State(p)
    assert s.cursor("owner/repo") is None
    s.advance("owner/repo", 5)
    assert s.cursor("owner/repo") == 5


def test_load_ignores_leftover_tmp_file(tmp_path: Path):
    """A previous crash may leave a state.json.tmp on disk. State should
    only read the canonical state.json and ignore the .tmp orphan."""
    p = tmp_path / "state.json"
    p.write_text('{"owner/repo": 50}')
    (tmp_path / "state.json.tmp").write_text("garbage")
    s = State(p)
    assert s.cursor("owner/repo") == 50
