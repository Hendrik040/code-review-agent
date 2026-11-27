"""risk_replay: the current router's stored Jev answers at other risk settings."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bugsinpy_bench" / "scripts"))

from risk_replay import repeat_runs, replay, tier_at  # noqa: E402


def test_tier_rule_matches_the_router():
    assert tier_at({"depth_probs": [0.9, 0.1, 0.0], "high_stakes": 0.1}, 0.15) == "light"
    assert tier_at({"depth_probs": [0.0, 0.85, 0.15], "high_stakes": 0.1}, 0.15) == "standard"  # boundary counts
    assert tier_at({"depth_probs": [0.0, 0.8, 0.2], "high_stakes": 0.1}, 0.15) == "deep"
    assert tier_at({"depth_probs": [0.9, 0.1, 0.0], "high_stakes": 0.5}, 0.15) == "deep"       # high-stakes override
    assert tier_at({"depth_probs": [], "high_stakes": None}, 0.15) == "deep"                    # Jev failed


def test_replay_at_the_current_setting_reproduces_the_logged_triage_result():
    r = replay(0.15)
    assert r["tiers"] == {"light": 2, "standard": 26, "deep": 72}
    assert (r["found"], r["cost_usd"]) == (42, pytest.approx(14.15, abs=0.01))


def test_replay_at_other_settings():
    assert (replay(0.25)["found"], replay(0.25)["cost_usd"]) == (42, pytest.approx(13.35, abs=0.01))
    assert (replay(0.70)["found"], replay(0.70)["cost_usd"]) == (40, pytest.approx(9.84, abs=0.01))
    assert replay(0.70)["random_expected_found"] == pytest.approx(37.2, abs=0.05)


def test_repeat_runs_on_the_30_pilot_bugs():
    r = repeat_runs()
    assert r["haiku"] == {"run1": 16, "run2": 18, "disagree": 4, "merged": 19}
    assert r["sonnet"] == {"run1": 17, "run2": 21, "disagree": 4, "merged": 21}
    assert r["opus_needed_with_second_haiku_run"] == {"bugs": 6, "found_by_second_haiku_run": 3}
