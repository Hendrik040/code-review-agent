"""pricing.py must reproduce what the Agent SDK harness actually billed.

Every stored Agent SDK run carries both the harness's `total_cost_usd`
and the usage dict it was billed for, so the rates in pricing.py can be
checked against ground truth without a model call. This is the check
that would have caught the constants sitting at the Opus 4 / 4.1 rates
(3x the `claude-opus-4-7` rate the reviewers run on).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import pricing
from scripts.headtohead import run_cost, stored_usage

ROOT = Path(__file__).resolve().parent.parent
AGENT_RUNS = sorted((ROOT / "agent_sdk" / "results").glob("run_*.txt"))

# run_035's harness figure is 2.0% above what its final usage dict costs
# (1.976591 vs 1.937641). Every other stored run matches to the
# microdollar, so this is that run's usage dict being incomplete, not a
# rate error.
USAGE_INCOMPLETE = {"run_035"}


def test_run_044_matches_harness_to_the_microdollar():
    usage = {
        "input_tokens": 8,
        "output_tokens": 13835,
        "cache_read_input_tokens": 179482,
        "cache_creation_input_tokens": 77307,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 77307,
            "ephemeral_1h_input_tokens": 0,
        },
    }
    assert pricing.cost_usd(usage) == pytest.approx(0.918825, abs=5e-7)


def test_one_hour_cache_writes_cost_twice_input():
    usage = {"cache_creation": {"ephemeral_1h_input_tokens": 1_000_000}}
    assert pricing.cost_usd(usage) == pytest.approx(2 * pricing.INPUT)


@pytest.mark.parametrize("path", AGENT_RUNS, ids=lambda p: p.stem)
def test_pricing_reproduces_harness_cost(path: Path):
    head = path.read_text().partition("# ---")[0]
    m = re.search(r"cost \(USD, harness-reported\): ([0-9.]+)", head)
    usage = stored_usage(path)
    assert m and usage, f"{path.name}: no harness cost / usage in header"
    harness = float(m.group(1))
    tolerance = 0.025 * harness if path.stem in USAGE_INCOMPLETE else 1e-6
    assert pricing.cost_usd(usage) == pytest.approx(harness, abs=tolerance)


def test_client_cost_is_recomputed_not_read_from_header():
    # run_052's header still says 4.939190 (written at the old 3x rate).
    path = ROOT / "client_sdk" / "results" / "run_052.txt"
    assert "4.939190" in path.read_text()
    assert run_cost("client", path) == pytest.approx(1.6463965, abs=5e-7)
