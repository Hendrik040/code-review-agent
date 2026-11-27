"""Phase 8 final-review fixes: noisy backends, upload failures, leftovers."""
from __future__ import annotations

import os
import time

from sandbox.repo import ExecResult
from shared import odis
from shared.agent_tools import build_review_context
from tests.test_phase8.helpers import FakeJev, make_name_clash_repo


class NoisyRepo:
    """Like DaytonaRepo: stderr is merged into stdout, warnings first."""

    def __init__(self, inner, fail_upload=False, garbage=False):
        self.inner, self.fail_upload, self.garbage = inner, fail_upload, garbage
        self.path = inner.path

    def exec(self, cmd, cwd=".", timeout=15):
        r = self.inner.exec(cmd, cwd=cwd, timeout=timeout)
        out = "warning: inexact rename detection was skipped\n" + r.stdout
        if self.garbage and " collect " in cmd:
            out = "not json at all"
        return ExecResult(stdout=out, stderr="", exit_code=r.exit_code)

    def upload_bytes(self, data, remote_path):
        if self.fail_upload:
            raise PermissionError("read-only")
        self.inner.upload_bytes(data, remote_path)


def _no_workfiles(repo) -> bool:
    return not (repo.path / ".git" / "odis").exists()


def test_stderr_merged_into_stdout_still_selects(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "jev")
    monkeypatch.setenv("IMPACT_MAX_CHARS", "2000")
    with make_name_clash_repo(n_rules=200) as inner:
        jev = FakeJev()
        out = build_review_context(NoisyRepo(inner), "HEAD~1", "HEAD", jev_client=jev)
        assert jev.calls and "<not_shown>" in out and _no_workfiles(inner)


def test_unparseable_collect_falls_back_to_one_shot(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "jev")
    with make_name_clash_repo(n_rules=20) as inner:
        out = build_review_context(NoisyRepo(inner, garbage=True), "HEAD~1", "HEAD", jev_client=FakeJev())
        assert odis.build_context(inner.path, "HEAD~1", "HEAD") in out
        assert _no_workfiles(inner)


def test_upload_failure_falls_back_and_cleans_up(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "jev")
    monkeypatch.setenv("IMPACT_MAX_CHARS", "2000")
    with make_name_clash_repo(n_rules=50) as inner:
        out = build_review_context(NoisyRepo(inner, fail_upload=True), "HEAD~1", "HEAD", jev_client=FakeJev())
        assert odis.build_context(inner.path, "HEAD~1", "HEAD") in out
        assert _no_workfiles(inner)


def test_collect_purges_stale_leftovers():
    with make_name_clash_repo(n_rules=2) as repo:
        repo.upload_bytes(b"{}", ".git/odis/deadbeef00.collected.json")
        old = time.time() - 3600
        os.utime(repo.path / ".git/odis/deadbeef00.collected.json", (old, old))
        repo.upload_bytes(b"{}", ".git/odis/cafe000000.collected.json")  # fresh: another call's
        assert repo.exec("python -m shared.odis_cli collect abcd1234 HEAD~1..HEAD", timeout=60).ok
        names = sorted(p.name for p in (repo.path / ".git/odis").iterdir())
        assert names == ["abcd1234.collected.json", "cafe000000.collected.json"]
