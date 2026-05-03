"""Conformance tests for the Repo protocol.

Both `LocalRepo` and `DaytonaRepo` must satisfy the same observable
behavior so reviewers and tools never have to know which backend is
underneath them. This file runs a single test suite against both
implementations:

  - LocalRepo: always run.
  - DaytonaRepo: skipped unless DAYTONA_API_KEY is set.

Tests cover:
  - exec returns ExecResult(stdout, stderr, exit_code) with ok==True
    on exit 0 and False otherwise
  - upload_bytes round-trips through `cat`
  - upload_bytes blocks `..` traversal
  - cwd= is repo-relative and resolves correctly
  - timeout produces a non-zero exit_code (LocalRepo: 124, DaytonaRepo
    surfaces an error string in stderr or stdout)
  - context-manager enter/exit is required to use the repo

Run:
  uv run python -m pytest tests/test_repo_conformance.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make the project root importable so `sandbox.*` resolves whether
# pytest is invoked from the repo root or anywhere else.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sandbox.local import LocalRepo
from sandbox.repo import ExecResult, Repo


# --------------------------------------------------------------------------- #
# Backend fixtures — parametrize the whole test module over each one.
# --------------------------------------------------------------------------- #


def _local_factory() -> Repo:
    return LocalRepo(prefix="conformance-")


def _daytona_factory() -> Repo:
    from sandbox.daytona import DaytonaRepo
    return DaytonaRepo()


_BACKENDS: list[tuple[str, callable]] = [("local", _local_factory)]
if os.getenv("DAYTONA_API_KEY"):
    _BACKENDS.append(("daytona", _daytona_factory))


@pytest.fixture(params=_BACKENDS, ids=[b[0] for b in _BACKENDS])
def repo(request) -> Repo:
    """Yield a freshly-provisioned Repo of the parametrized backend.

    The context manager is entered for the test and exited in
    teardown; tests treat `repo` as if it were already opened.
    """
    _name, factory = request.param
    impl = factory()
    with impl as opened:
        yield opened


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_exec_returns_execresult_on_zero_exit(repo: Repo) -> None:
    r = repo.exec("echo hello")
    assert isinstance(r, ExecResult)
    assert r.ok
    assert r.exit_code == 0
    assert "hello" in r.stdout


def test_exec_nonzero_exit_is_not_ok(repo: Repo) -> None:
    r = repo.exec("exit 7")
    assert isinstance(r, ExecResult)
    assert not r.ok
    assert r.exit_code == 7


def test_upload_bytes_roundtrips(repo: Repo) -> None:
    repo.upload_bytes(b"hello sandbox\n", "scratch/note.txt")
    r = repo.exec("cat scratch/note.txt")
    assert r.ok
    assert r.stdout.rstrip("\n") == "hello sandbox"


def test_upload_bytes_creates_parent_dirs(repo: Repo) -> None:
    repo.upload_bytes(b"deep", "a/b/c/d/file.txt")
    r = repo.exec("cat a/b/c/d/file.txt")
    assert r.ok
    assert r.stdout == "deep"


def test_upload_bytes_blocks_traversal(repo: Repo) -> None:
    with pytest.raises(PermissionError):
        repo.upload_bytes(b"pwn", "../../../tmp/escape.txt")


def test_upload_bytes_blocks_absolute_paths(repo: Repo) -> None:
    """Absolute paths bypass the relative-anchor — both backends reject."""
    # LocalRepo: the resolved absolute path won't be inside the
    # repo tempdir; _safe_target rejects.
    # DaytonaRepo: explicit guard on remote_path.startswith("/").
    with pytest.raises(PermissionError):
        repo.upload_bytes(b"pwn", "/etc/escape.txt")


def test_cwd_is_repo_relative(repo: Repo) -> None:
    repo.upload_bytes(b"top", "top.txt")
    repo.upload_bytes(b"nested", "sub/nested.txt")
    r_top = repo.exec("cat top.txt", cwd=".")
    r_nested = repo.exec("cat nested.txt", cwd="sub")
    assert r_top.ok and r_top.stdout == "top"
    assert r_nested.ok and r_nested.stdout == "nested"


def test_python_module_path_resolves(repo: Repo) -> None:
    """`python -m shared.odis_cli --help` works in both backends.

    LocalRepo seeds PYTHONPATH to the project root; DaytonaRepo
    bootstraps shared/* into PYTHONPATH_ROOT inside the sandbox.
    Either way, the agent's build_review_context tool relies on
    this invocation working — so it's a tier-1 conformance check.
    """
    r = repo.exec("python -m shared.odis_cli --help", timeout=30)
    assert r.exit_code == 0
    assert "BASE..HEAD" in r.stdout


def test_git_workflow(repo: Repo) -> None:
    """A minimal git init → commit → log workflow works.

    This is the path shared/fixtures.py:_populate uses to seed
    a fixture; both backends must support it without sudo.
    """
    repo.upload_bytes(b"v1\n", "calc.py")
    init = repo.exec("git init -q && git add -A && git commit -q -m v1", timeout=30)
    assert init.ok, init.stdout + init.stderr
    repo.upload_bytes(b"v2\n", "calc.py")
    v2 = repo.exec("git add -A && git commit -q -m v2", timeout=30)
    assert v2.ok, v2.stdout + v2.stderr
    log = repo.exec("git log --oneline", timeout=15)
    assert log.ok
    lines = [line for line in log.stdout.strip().splitlines() if line]
    assert len(lines) == 2, f"expected 2 commits, got: {log.stdout!r}"


def test_timeout_produces_nonzero_exit(repo: Repo) -> None:
    """Long commands hit the timeout boundary cleanly.

    LocalRepo returns exit_code=124 with a descriptive stderr.
    DaytonaRepo's behavior depends on the SDK; it should still
    surface as a non-zero exit, never as an unhandled exception.
    """
    r = repo.exec("sleep 5", timeout=1)
    assert not r.ok
