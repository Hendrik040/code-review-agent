import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bugsinpy_bench" / "scripts"))

from block_rules import auc, block_risk, decide, norm_levels, sweep  # noqa: E402


def test_norm_levels_int_and_str_keys():
    assert norm_levels({0: 0.1, "1": 0.9}, 3) == [0.1, 0.9, 0.0]
    assert norm_levels({0: 0.2, 1: 0.2}, 2) is None


def test_block_risk_max_over_blocks_and_questions():
    a = {"answers": {"precision_logic": 0.1, "state_tracking": 0.7, "error_path": 0.0,
                     "contract_change": 0.0, "value_domain": 0.0, "async_flow": 0.9,
                     "verify_effort": [0.5, 0.3, 0.2]}}
    b = {"answers": {"precision_logic": 0.2, "state_tracking": 0.0, "error_path": 0.0,
                     "contract_change": 0.0, "value_domain": 0.0, "async_flow": 0.0,
                     "verify_effort": [0.0, 0.2, 0.8]}}
    assert block_risk([a, b]) == 0.8  # async_flow is NOT in Q1-Q5
    assert block_risk([]) == 0.0
    assert block_risk([{"error": "timeout"}]) == 1.0


def test_decide_rule():
    low = {"blocks": [], "pr": {"change_kind": [0.9, 0.05, 0.05, 0.0], "high_stakes": 0.1}}
    assert decide(low, 0.5) == "light"
    std = {"blocks": [], "pr": {"change_kind": [0.0, 0.2, 0.7, 0.1], "high_stakes": 0.1}}
    assert decide(std, 0.5) == "standard"
    deep_ck = {"blocks": [], "pr": {"change_kind": [0.0, 0.1, 0.6, 0.3], "high_stakes": 0.1}}
    assert decide(deep_ck, 0.5) == "deep"
    risky = {"blocks": [{"error": "x"}], "pr": {"change_kind": [0.9, 0.1, 0, 0], "high_stakes": 0.0}}
    assert decide(risky, 0.5) == "deep"
    hs = {"blocks": [], "pr": {"change_kind": [1, 0, 0, 0], "high_stakes": 0.5}}
    assert decide(hs, 0.5) == "deep"
    broken = {"blocks": [], "pr": {"change_kind": None, "high_stakes": 0.0}}
    assert decide(broken, 0.5) == "deep"


def test_auc():
    assert auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert auc([0.5], [0.5]) == 0.5
    assert math.isnan(auc([], [0.1]))


def test_sweep_counts_found_and_cost():
    entries = {"x#1": {"blocks": [{"error": "e"}], "pr": {"change_kind": [1, 0, 0, 0], "high_stakes": 0}},
               "x#2": {"blocks": [], "pr": {"change_kind": [1, 0, 0, 0], "high_stakes": 0}}}
    outcomes = {"x#1": {"light": {"found": False, "cost_usd": 0.01}, "standard": {"found": False, "cost_usd": 0.05},
                        "deep": {"found": True, "cost_usd": 0.2}},
                "x#2": {"light": {"found": True, "cost_usd": 0.01}, "standard": {"found": True, "cost_usd": 0.05},
                        "deep": {"found": True, "cost_usd": 0.2}}}
    (r,) = sweep(entries, outcomes, [0.5])
    assert r == {"T": 0.5, "found": 2, "cost_usd": 0.21, "tiers": {"light": 1, "standard": 0, "deep": 1}}
