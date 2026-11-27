"""Phase 8 Task 5 — build_review_context end to end through LocalRepo."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared import odis
from shared.agent_tools import build_review_context
from shared.fixtures import CONTRACT_MISMATCH, materialize
from tests.test_phase8.helpers import FakeJev, git, make_name_clash_repo

GOLDEN = Path(__file__).parent / "golden"


@pytest.mark.parametrize("mode", ["jev", "cap", "off"])
def test_small_fixture_identical_in_every_mode(mode, monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", mode)
    jev = FakeJev()
    with materialize(CONTRACT_MISMATCH) as m:
        out = build_review_context(m.repo, m.base_ref, m.head_ref, jev_client=jev)
    assert out == (GOLDEN / "contract_mismatch.md").read_text()
    assert jev.calls == []


def test_name_clash_repo_is_bounded_and_annotated(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "jev")
    monkeypatch.setenv("IMPACT_MAX_CHARS", "2000")
    with make_name_clash_repo(n_rules=200) as repo:
        full = odis.build_context(repo.path, "HEAD~1", "HEAD")
        jev = FakeJev({})
        out = build_review_context(repo, "HEAD~1", "HEAD", jev_client=jev)
        assert jev.calls
        assert len(out) < len(full) / 5 and "<not_shown>" in out
        assert "judged unrelated" in out
        assert not (repo.path / ".git" / "odis").exists()


def test_jev_choice_is_rendered_in_full(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "jev")
    monkeypatch.setenv("IMPACT_MAX_CHARS", "2000")
    with make_name_clash_repo(n_rules=200) as repo:
        c = odis.collect(repo.path, "HEAD~1", "HEAD")
        target = next(x for x in c.candidates if x.file == "pkg/utils.py")
        out = build_review_context(repo, "HEAD~1", "HEAD", jev_client=FakeJev({target.id: 0.95}))
        assert target.text in out


def test_off_mode_is_todays_output(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "off")
    with make_name_clash_repo(n_rules=50) as repo:
        assert build_review_context(repo, "HEAD~1", "HEAD") == odis.build_context(repo.path, "HEAD~1", "HEAD")


def test_docs_only_diff_unchanged_and_no_jev(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "jev")
    with make_name_clash_repo(n_rules=2) as repo:
        repo.upload_bytes(b"hi\n", "README.md")
        git(repo, "add -A")
        git(repo, "commit -qm docs")
        jev = FakeJev()
        out = build_review_context(repo, "HEAD~1", "HEAD", jev_client=jev)
        assert out == odis.build_context(repo.path, "HEAD~1", "HEAD")
        assert jev.calls == []


def test_long_diff_truncated_for_jev_only(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "jev")
    monkeypatch.setenv("IMPACT_MAX_CHARS", "2000")
    monkeypatch.setenv("CONTEXT_MAX_CHARS", "10000000")
    with make_name_clash_repo(n_rules=200) as repo:
        src = (repo.path / "pkg/rules/new.py").read_text()
        repo.upload_bytes((src + "\n" + "# pad\n" * 6000).encode(), "pkg/rules/new.py")
        git(repo, "add -A")
        git(repo, "commit -qm pad")
        jev = FakeJev()
        out = build_review_context(repo, "HEAD~2", "HEAD", jev_client=jev)
        assert jev.calls and all(len(s["diff"]) <= 24000 for s, _ in jev.calls)
        assert out.count("+# pad") == 6000


def test_total_guard_drops_changed_section(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "cap")
    monkeypatch.setenv("CONTEXT_MAX_CHARS", "100")
    with materialize(CONTRACT_MISMATCH) as m:
        out = build_review_context(m.repo, m.base_ref, m.head_ref)
    assert "(Omitted to fit the context budget" in out
    assert out != (GOLDEN / "contract_mismatch.md").read_text()


def test_collect_failure_keeps_todays_error_format(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "jev")
    with make_name_clash_repo(n_rules=2) as repo:
        out = build_review_context(repo, "nope", "HEAD")
        assert out.startswith("Error: build_review_context failed (exit ")


def test_selection_crash_still_returns_context(monkeypatch):
    import shared.impact_select as sel
    monkeypatch.setenv("IMPACT_SELECT", "jev")
    monkeypatch.setenv("IMPACT_MAX_CHARS", "2000")

    calls = {"n": 0}
    real = sel.decide

    def flaky(doc, cfg, *, client=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(doc, cfg, client=client)

    monkeypatch.setattr(sel, "decide", flaky)
    with make_name_clash_repo(n_rules=200) as repo:
        out = build_review_context(repo, "HEAD~1", "HEAD", jev_client=FakeJev())
        assert "not ranked for relevance" in out and calls["n"] == 2
