"""merge_scores: Martian results when several stored reviews of a PR are merged."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "martian_bench" / "scripts"))

from merge_scores import merged  # noqa: E402


def test_single_arms_match_the_logged_scores():
    s = merged(["sonnet"])
    assert (s["goldens"], s["of"], s["findings"]) == (13, 31, 20)
    assert s["f1"] == pytest.approx(0.510, abs=0.001)
    assert merged(["opus"])["goldens"] == 9 and merged(["haiku"])["goldens"] == 7


def test_merged_arms_count_a_golden_once_and_pool_the_findings():
    hs = merged(["haiku", "sonnet"])
    assert (hs["goldens"], hs["findings"]) == (13, 31)   # Haiku adds no golden to Sonnet
    assert hs["precision"] == pytest.approx(19 / 31, abs=0.001)
    ho = merged(["haiku", "opus"])
    assert (ho["goldens"], ho["findings"]) == (12, 28)
    assert merged(["haiku", "sonnet", "opus"])["goldens"] == 15
