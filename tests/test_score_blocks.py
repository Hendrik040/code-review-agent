import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bugsinpy_bench" / "scripts"))

from score_blocks import bugsinpy_outcomes, current_router_auc, martian_outcomes, opus_needed_split  # noqa: E402


def test_opus_needed_split_matches_step_10():
    pos, neg = opus_needed_split(bugsinpy_outcomes())
    assert len(pos) == 14 and len(neg) == 35


def test_current_router_auc_is_0_27():
    assert round(current_router_auc(), 2) == 0.27


def test_martian_outcomes_cover_10_prs_and_31_goldens():
    m = martian_outcomes()
    assert len(m) == 10
    assert sum(v["deep"]["n_goldens"] for v in m.values()) == 31
    assert sum(v["deep"]["matched_goldens"] for v in m.values()) == 9
    assert sum(v["standard"]["matched_goldens"] for v in m.values()) == 13
