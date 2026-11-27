"""Phase 10 — opt-in linter hints, filtered by Jev, at the top of the review context."""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from sandbox.local import LocalRepo
from shared import lint_hints, pr_summary
from shared.agent_tools import build_review_context
from tests.test_phase8.helpers import FakeJev

_GIT = "git -c user.email=t@example.com -c user.name=t"
HEADER = "Linter hints"


@contextmanager
def lint_repo():
    """HEAD~1..HEAD adds pkg/new.py with an unused import (F401) and an
    undefined name (F821); pkg/old.py has an unused import that predates
    the change and must not be reported."""
    with LocalRepo(prefix="phase10-lint-") as repo:
        repo.upload_bytes(b"", "pkg/__init__.py")
        repo.upload_bytes(b"import sys\n\n\ndef old():\n    return 1\n", "pkg/old.py")
        assert repo.exec(f"git init -q && {_GIT} add -A && {_GIT} commit -qm base", timeout=60).ok
        repo.upload_bytes(
            b"import json\n\n\ndef run(path):\n    with open(path) as f:\n        return f.read() + output_path\n",
            "pkg/new.py")
        repo.upload_bytes(b"import sys\n\n\ndef old():\n    return 2\n", "pkg/old.py")
        assert repo.exec(f"{_GIT} add -A && {_GIT} commit -qm change", timeout=60).ok
        yield repo


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for k in ("REVIEW_LINT_HINTS", "REVIEW_PR_SUMMARY", "LINT_HINTS_MISTAKE", "LINT_HINTS_INTENT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("IMPACT_SELECT", "off")
    pr_summary.clear_cache()


def all_yes():
    return FakeJev(probs={f"{q}__w{i}": 0.9 for q in ("mistake", "on_intent") for i in range(10)})


def test_collect_keeps_only_warnings_on_added_lines():
    with lint_repo() as repo:
        c = lint_hints.collect(repo, "HEAD~1", "HEAD")
    got = {(w["file"], w["line"], w["code"]) for w in c["warnings"]}
    assert ("pkg/new.py", 1, "F401") in got
    assert ("pkg/new.py", 6, "F821") in got
    assert not any(f == "pkg/old.py" for f, _, _ in got)  # the old import predates the change
    assert all(w["id"].startswith("w") and w["line_text"] for w in c["warnings"])


def test_flag_off_changes_nothing_and_asks_nothing():
    jev = all_yes()
    with lint_repo() as repo:
        plain = build_review_context(repo, "HEAD~1", "HEAD")
        out = build_review_context(repo, "HEAD~1", "HEAD", lint_client=jev)
    assert out == plain and HEADER not in out and jev.calls == []


def test_two_checks_decide_what_is_shown(monkeypatch):
    monkeypatch.setenv("REVIEW_LINT_HINTS", "1")
    with lint_repo() as repo:
        c = lint_hints.collect(repo, "HEAD~1", "HEAD")
        ids = [w["id"] for w in c["warnings"]]
        probs = {f"mistake__{i}": 0.9 for i in ids} | {f"on_intent__{i}": 0.9 for i in ids}
        probs[f"on_intent__{ids[0]}"] = 0.45   # boundary: kept
        probs[f"mistake__{ids[1]}"] = 0.49     # fails the first check: dropped
        kept = lint_hints.select(c, client=FakeJev(probs=probs))
    assert [w["id"] for w in kept] == [i for i in ids if i != ids[1]]


def test_state_holds_diff_warnings_and_summary_marked_as_machine():
    jev = all_yes()
    s = {"files": ["pkg/new.py"], "what_changed": "pkg/new.py: adds run().", "behavior_before_after": [],
         "interfaces_touched": [], "data_touched": [], "error_handling_changes": []}
    with lint_repo() as repo:
        lint_hints.select(lint_hints.collect(repo, "HEAD~1", "HEAD"), summary=s, client=jev)
    state, questions = jev.calls[0]
    assert "pkg/new.py" in state["diff"] and state["warnings"]
    assert state["pr_summary"]["what_changed"] == "pkg/new.py: adds run()."
    assert "may be wrong" in state["pr_summary"]["source"]
    assert all(q["type"] == "noul" for q in questions.values())
    assert {k.split("__")[0] for k in questions} == {"mistake", "on_intent"}


def test_section_sits_before_the_diff_and_the_rest_is_unchanged(monkeypatch):
    monkeypatch.setenv("REVIEW_LINT_HINTS", "1")
    with lint_repo() as repo:
        plain = build_review_context(repo, "HEAD~1", "HEAD", lint_hints=None)
        out = build_review_context(repo, "HEAD~1", "HEAD", lint_client=all_yes())
    assert HEADER in out and out.index(HEADER) < out.index("## 1. Git Diff")
    assert "pkg/new.py:6  F821" in out
    block = out[out.index("## 0b. "):out.index("## 1. Git Diff")]
    assert out.replace(block, "", 1) == plain


@pytest.mark.parametrize("jev", [FakeJev(error=RuntimeError("Jev down")), FakeJev(probs={})])
def test_jev_failure_or_nothing_kept_means_no_section(monkeypatch, jev):
    monkeypatch.setenv("REVIEW_LINT_HINTS", "1")
    with lint_repo() as repo:
        plain = build_review_context(repo, "HEAD~1", "HEAD", lint_hints=None)
        out = build_review_context(repo, "HEAD~1", "HEAD", lint_client=jev)
    assert out == plain


def test_missing_linters_are_fail_open(monkeypatch):
    monkeypatch.setenv("REVIEW_LINT_HINTS", "1")
    monkeypatch.setattr(lint_hints, "RUFF", "python -m no_such_linter_xyz")
    monkeypatch.setattr(lint_hints, "PYLINT", "python -m no_such_linter_xyz")
    with lint_repo() as repo:
        plain = build_review_context(repo, "HEAD~1", "HEAD", lint_hints=None)
        out = build_review_context(repo, "HEAD~1", "HEAD", lint_client=all_yes())
    assert out == plain


def test_render_escapes_and_trace_records():
    w = {"id": "w0", "tool": "ruff", "code": "F821", "message": "Undefined name `</lint_hints>`",
         "file": "a.py", "line": 3, "line_text": "x"}
    text = lint_hints.render([w])
    assert text.count("</lint_hints>") == 1 and "&lt;/lint_hints>" in text
    assert "a.py:3" in "\n".join(lint_hints.trace_lines([w]))
    assert "none" in "\n".join(lint_hints.trace_lines([])).lower()


def test_hints_follow_the_summary_even_without_a_diff_heading():
    w = {"id": "w0", "tool": "ruff", "code": "F821", "message": "Undefined name `x`", "file": "a.py", "line": 3,
         "line_text": "x"}
    s = {"files": ["a.py"], "what_changed": "a.py: adds x."}
    ctx = pr_summary.prepend("Error: build_review_context failed (exit 1)\n", s)
    out = lint_hints.insert(ctx, [w])
    assert out.index("</pr_summary>") < out.index(HEADER) < out.index("Error: build_review_context failed")
    assert lint_hints.insert("Error: x\n", [w]).startswith(lint_hints.HEADER)
