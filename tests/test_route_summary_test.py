"""route_summary_test: what Jev is sent in each arm, and the scoring."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bugsinpy_bench" / "scripts"))

from route_summary_test import ask, base_state, score_answers, state_for, summary_section  # noqa: E402

DIFF = "diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n@@ -1 +1,2 @@\n-x\n+y\n+z\n"
SUMMARY = {"what_changed": "pkg/a.py: x becomes y and z.", "behavior_before_after": ["returned x → returns y"],
           "interfaces_touched": [], "data_touched": [], "error_handling_changes": ["raises ValueError on z"]}


def test_control_state_is_the_routers_state():
    assert base_state("Fix a", DIFF) == (
        "Pull request title: Fix a\nFiles changed (lines added, lines removed, path):\n2\t1\tpkg/a.py\nDiff:\n" + DIFF)
    assert state_for("control", "Fix a", DIFF, SUMMARY) == base_state("Fix a", DIFF)


def test_long_diff_is_cut_and_says_so():
    s = base_state("t", DIFF + "+" + "q" * 30000, max_chars=24000)
    assert f"Diff (first 24000 of {len(DIFF) + 30001} characters):\n" in s
    assert len(s.split("characters):\n", 1)[1]) == 24000


def test_summary_arm_adds_one_section_after_the_title():
    s = state_for("summary", "Fix a", DIFF, SUMMARY)
    head, rest = s.split("Files changed (lines added, lines removed, path):", 1)
    assert head.startswith("Pull request title: Fix a\n")
    assert summary_section(SUMMARY) in head
    assert "pkg/a.py: x becomes y and z." in head and "returned x → returns y" in head
    assert "raises ValueError on z" in head and "Interfaces" not in head   # empty lists are left out
    assert "Files changed (lines added, lines removed, path):" + rest == base_state("Fix a", DIFF).split("\n", 1)[1]
    with pytest.raises(ValueError):
        state_for("other", "t", DIFF, SUMMARY)


def test_ask_parses_probabilities_and_records_errors():
    class Jev:
        def system_one(self, state, questions):
            return SimpleNamespace(
                answers={"depth": SimpleNamespace(probabilities={0: 0.1, 1: 0.7, 2: 0.2}),
                         "high_stakes": SimpleNamespace(noul=0.05)},
                usage=SimpleNamespace(input_tokens=500, output_tokens=9))
    qs = {"depth": {"type": "score", "criteria": ["a", "b", "c"]}, "high_stakes": {"type": "noul"}}
    assert ask("s", qs, Jev()) == {"depth_probs": [0.1, 0.7, 0.2], "high_stakes": 0.05, "input_tokens": 500}

    class Broken:
        def system_one(self, state, questions):
            raise TimeoutError("x")
    assert ask("s", qs, Broken()) == {"error": "TimeoutError"}


def test_score_counts_tiers_found_and_cost():
    bugs = {"a#1": {"haiku55_medium": {"found": False, "cost_usd": 0.01}, "sonnet55_high": {"found": True, "cost_usd": 0.05},
                    "opus55_high": {"found": True, "cost_usd": 0.2}},
            "a#2": {"haiku55_medium": {"found": False, "cost_usd": 0.01}, "sonnet55_high": {"found": False, "cost_usd": 0.05},
                    "opus55_high": {"found": True, "cost_usd": 0.3}}}
    answers = {"a#1": {"depth_probs": [0.0, 0.9, 0.1], "high_stakes": 0.0},
               "a#2": {"error": "TimeoutError"}}          # an error routes deep, as in the router
    r = score_answers(answers, bugs, 0.15)
    assert r["tiers"] == {"light": 0, "standard": 1, "deep": 1}
    assert (r["found"], r["cost_usd"]) == (2, 0.35)
