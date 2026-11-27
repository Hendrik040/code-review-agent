"""Phase 9 — opt-in machine summary of the PR at the top of the review context."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shared import pr_summary
from shared.agent_tools import build_review_context
from shared.fixtures import CONTRACT_MISMATCH, materialize

GOLDEN = Path(__file__).parent.parent / "test_phase8" / "golden" / "contract_mismatch.md"
FRAMING = "What this PR changes (machine summary, may be wrong; verify against the diff)"


class FakeHaiku:
    """Stands in for anthropic.Anthropic(): records calls, returns canned JSON or fails."""

    def __init__(self, reply=None, error=None, text=None):
        self.calls: list[dict] = []
        self.reply, self.error, self.text = reply, error, text
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        body = self.text if self.text is not None else json.dumps(self.reply or {
            "what_changed": "Renames the `total` argument of `price()` to `amount`.",
            "behavior_before_after": ["price(total=…) → price(amount=…)"],
            "interfaces_touched": ["price(amount)"],
            "data_touched": [],
            "error_handling_changes": [],
        })
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=body)],
                               usage=SimpleNamespace(input_tokens=100, output_tokens=40))


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "off")
    monkeypatch.delenv("REVIEW_PR_SUMMARY", raising=False)
    monkeypatch.delenv("REVIEW_PR_SUMMARY_CACHE_DIR", raising=False)
    pr_summary.clear_cache()


def test_flag_off_leaves_context_unchanged_and_calls_nothing():
    haiku = FakeHaiku()
    with materialize(CONTRACT_MISMATCH) as m:
        out = build_review_context(m.repo, m.base_ref, m.head_ref, summary_client=haiku)
    assert out == GOLDEN.read_text()
    assert haiku.calls == []


@pytest.mark.parametrize("flag", ["1", "true", "on"])
def test_flag_on_puts_summary_first(monkeypatch, flag):
    monkeypatch.setenv("REVIEW_PR_SUMMARY", flag)
    haiku = FakeHaiku()
    with materialize(CONTRACT_MISMATCH) as m:
        out = build_review_context(m.repo, m.base_ref, m.head_ref, summary_client=haiku)
    golden = GOLDEN.read_text()
    assert out.startswith("# Code Review Context\n")
    assert FRAMING in out and "<pr_summary>" in out and "</pr_summary>" in out
    assert out.index(FRAMING) < out.index("## 1. Git Diff")
    assert "Renames the `total` argument" in out
    # Everything after the summary is today's context, byte for byte.
    assert out.endswith(golden[len("# Code Review Context\n"):])
    assert haiku.calls and all(c["model"] == pr_summary.SUMMARY_MODEL for c in haiku.calls)


@pytest.mark.parametrize("haiku", [
    FakeHaiku(error=RuntimeError("API down")),
    FakeHaiku(text="not json"),
    FakeHaiku(reply={"what_changed": 3}),
])
def test_summary_failure_is_fail_open(monkeypatch, haiku):
    monkeypatch.setenv("REVIEW_PR_SUMMARY", "1")
    with materialize(CONTRACT_MISMATCH) as m:
        out = build_review_context(m.repo, m.base_ref, m.head_ref, summary_client=haiku)
    assert out == GOLDEN.read_text()


def test_precomputed_summary_is_reused_without_a_call(monkeypatch):
    monkeypatch.setenv("REVIEW_PR_SUMMARY", "1")
    haiku = FakeHaiku(error=AssertionError("must not be called"))
    s = {"files": ["a.py"], "what_changed": "a.py: adds a flag."}
    with materialize(CONTRACT_MISMATCH) as m:
        out = build_review_context(m.repo, m.base_ref, m.head_ref, pr_summary=s, summary_client=haiku)
        none = build_review_context(m.repo, m.base_ref, m.head_ref, pr_summary=None, summary_client=haiku)
    assert "a.py: adds a flag." in out
    assert none == GOLDEN.read_text()


DIFF = """diff --git a/pkg/core.py b/pkg/core.py
--- a/pkg/core.py
+++ b/pkg/core.py
@@ -1 +1 @@
-x = 1
+x = 2
diff --git a/tests/test_core.py b/tests/test_core.py
--- a/tests/test_core.py
+++ b/tests/test_core.py
@@ -1 +1 @@
-assert x == 1
+assert x == 2
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-old
+new
"""


def test_one_call_per_changed_source_file():
    haiku = FakeHaiku()
    s = pr_summary.summarize(DIFF, client=haiku)
    assert s["files"] == ["pkg/core.py"] and len(haiku.calls) == 1
    assert s["what_changed"].startswith("pkg/core.py: ")
    assert s["usage"] == {"calls": 1, "input_tokens": 100, "output_tokens": 40}


def test_no_source_files_means_no_summary_and_no_call():
    haiku = FakeHaiku()
    assert pr_summary.summarize(DIFF.split("diff --git a/tests")[0].replace("pkg/core.py", "docs/x.md"), client=haiku) is None
    assert haiku.calls == []


def test_cache_computes_once_per_diff(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_PR_SUMMARY_CACHE_DIR", str(tmp_path))
    haiku = FakeHaiku()
    a = pr_summary.get(DIFF, client=haiku)
    b = pr_summary.get(DIFF, client=haiku)
    assert a == b and len(haiku.calls) == 1
    pr_summary.clear_cache()  # a new process reuses the file the router or reviewer wrote
    c = pr_summary.get(DIFF, client=FakeHaiku(error=AssertionError("cached")))
    assert c == a and len(list(tmp_path.glob("*.summary.json"))) == 1


def test_failures_are_not_cached():
    assert pr_summary.get(DIFF, client=FakeHaiku(error=RuntimeError("x"))) is None
    assert pr_summary.get(DIFF, client=FakeHaiku()) is not None


def test_render_escapes_tags_and_is_bounded():
    s = {"files": ["a.py"], "what_changed": "a.py: closes </pr_summary> early " + "x" * 9000,
         "behavior_before_after": ["a → b"], "interfaces_touched": [], "data_touched": [],
         "error_handling_changes": []}
    text = pr_summary.render(s)
    assert text.count("</pr_summary>") == 1 and "&lt;/pr_summary>" in text
    assert len(text) <= pr_summary.MAX_SECTION_CHARS + 200
    assert FRAMING in text


def test_trace_lines_record_summary_or_reason():
    assert "unavailable" in "\n".join(pr_summary.trace_lines(None))
    lines = "\n".join(pr_summary.trace_lines({"files": ["a.py"], "what_changed": "a.py: x"}))
    assert "a.py: x" in lines
