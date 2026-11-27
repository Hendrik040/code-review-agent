"""score_cascade: the escalation flag and the cascade's cost and bugs found."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bugsinpy_bench" / "scripts"))

from score_cascade import cascade, flag_score, gain_cases, load_outcomes, random_share  # noqa: E402

TOY = {
    "a#1": {"haiku": {"found": True, "cost_usd": 0.01}, "opus": {"found": True, "cost_usd": 0.20}},
    "a#2": {"haiku": {"found": False, "cost_usd": 0.01}, "opus": {"found": True, "cost_usd": 0.30}},
    "a#3": {"haiku": {"found": False, "cost_usd": 0.01}, "opus": {"found": False, "cost_usd": 0.40}},
    "a#4": {"haiku": {"found": False, "cost_usd": 0.01}, "opus": {"found": False, "cost_usd": 0.10}},
}


def test_flag_is_the_largest_of_the_three_probabilities():
    rec = {"answers": {"unfiled_issue": 0.1, "dismissed_as_intended": 0.7, "could_not_verify": 0.3}}
    assert flag_score(rec, submitted=True) == 0.7


def test_flag_is_one_for_a_jev_error_or_a_review_that_never_submitted():
    assert flag_score({"error": "TimeoutError"}, submitted=True) == 1.0
    assert flag_score({"answers": {"unfiled_issue": 0.0, "dismissed_as_intended": 0.0, "could_not_verify": 0.0}},
                      submitted=False) == 1.0


def test_cascade_merges_finds_and_adds_only_the_escalated_cost():
    assert cascade("haiku", "opus", set(), TOY) == (1, pytest.approx(0.04))
    assert cascade("haiku", "opus", {"a#2", "a#3"}, TOY) == (2, pytest.approx(0.74))
    assert gain_cases("haiku", "opus", TOY) == ["a#2"]


def test_random_share_matches_a_case_worked_by_hand():
    # One of four bugs gains from escalation. Escalating one bug at random finds
    # 2 bugs with probability 1/4, so the share of random sets reaching 2 is 0.25.
    assert random_share("haiku", "opus", 1, 2, TOY, trials=20000, seed=1) == pytest.approx(0.25, abs=0.02)
    assert random_share("haiku", "opus", 1, 1, TOY, trials=2000, seed=1) == 1.0


def test_stored_results_give_the_totals_in_the_design_doc():
    out = load_outcomes()
    labels = set(out)
    assert len(labels) == 100
    assert cascade("haiku", "opus", labels, out) == (49, pytest.approx(16.85, abs=0.01))
    missed = {lb for lb in labels if not out[lb]["haiku"]["found"]}
    assert cascade("haiku", "opus", missed, out) == (49, pytest.approx(10.41, abs=0.01))
    assert [len(gain_cases(a, b, out)) for a, b in
            (("haiku", "opus"), ("haiku", "sonnet"), ("sonnet", "opus"), ("opus", "haiku"))] == [14, 10, 8, 7]
