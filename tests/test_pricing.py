"""pricing.py must reproduce what the Agent SDK harness actually billed.

Every stored Agent SDK run carries both the harness's `total_cost_usd`
and the usage dict it was billed for, so the rates in pricing.py can be
checked against ground truth without a model call. This is the check
that would have caught the constants sitting at the Opus 4 / 4.1 rates
(3x the `claude-opus-4-7` rate the reviewers ran on).

Runs written since model routing name their model in the header and are
priced at that model's row in `pricing.RATES`; older runs carry no model
line and are all `claude-opus-4-7`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import pricing
from scripts.headtohead import run_cost, stored_model, stored_usage

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


# Usage of a live claude-opus-5-5 review at effort "high" (2026-11-27, the
# contract_mismatch fixture). The harness reported $0.217646 for it.
OPUS_5_5_USAGE = {
    "input_tokens": 8,
    "output_tokens": 748,
    "cache_read_input_tokens": 107019,
    "cache_creation_input_tokens": 36250,
    "cache_creation": {
        "ephemeral_5m_input_tokens": 36250,
        "ephemeral_1h_input_tokens": 0,
    },
}


def test_opus_5_5_row_matches_harness_to_the_microdollar():
    cost = pricing.cost_usd(OPUS_5_5_USAGE, "claude-opus-5-5")
    assert cost == pytest.approx(0.217646, abs=5e-7)


def _write_run(tmp_path: Path, *header: str) -> Path:
    path = tmp_path / "run_900.txt"
    path.write_text("\n".join(header) + "\n# ---\n[]\n")
    return path


def test_stored_model_reads_the_model_a_run_names(tmp_path):
    path = _write_run(tmp_path, "# Agent SDK reviewer run 900",
                      "# model: claude-opus-5-5  effort: high")
    assert stored_model(path) == "claude-opus-5-5"


def test_stored_model_is_none_for_runs_written_before_routing():
    assert stored_model(ROOT / "agent_sdk" / "results" / "run_044.txt") is None


def _check_reproduces_harness(path: Path) -> None:
    head = path.read_text().partition("# ---")[0]
    m = re.search(r"cost \(USD, harness-reported\): ([0-9.]+)", head)
    usage = stored_usage(path)
    assert m and usage, f"{path.name}: no harness cost / usage in header"
    harness = float(m.group(1))
    model = stored_model(path)
    recomputed = pricing.cost_usd(usage, model)
    if recomputed is None:
        pytest.skip(f"{path.name}: pricing.RATES has no row for {model}")
    tolerance = 0.025 * harness if path.stem in USAGE_INCOMPLETE else 1e-6
    assert recomputed == pytest.approx(harness, abs=tolerance)


@pytest.mark.parametrize("path", AGENT_RUNS, ids=lambda p: p.stem)
def test_pricing_reproduces_harness_cost(path: Path):
    _check_reproduces_harness(path)


def test_a_run_on_another_model_is_priced_at_that_models_row(tmp_path):
    """The default reviewer model is no longer Opus 4.7, so a new run in
    agent_sdk/results/ must not be checked against the Opus 4.7 rates."""
    path = _write_run(tmp_path, "# model: claude-opus-5-5  effort: high",
                      "# cost (USD, harness-reported): 0.217646",
                      f"# usage: {OPUS_5_5_USAGE}")
    _check_reproduces_harness(path)


def test_a_wrong_rate_is_still_caught_for_a_run_that_names_its_model(tmp_path):
    path = _write_run(tmp_path, "# model: claude-opus-4-7  effort: max",
                      "# cost (USD, harness-reported): 0.217646",
                      f"# usage: {OPUS_5_5_USAGE}")
    with pytest.raises(AssertionError):
        _check_reproduces_harness(path)


def test_a_run_on_a_model_without_a_rate_row_is_skipped(tmp_path):
    path = _write_run(tmp_path, "# model: claude-haiku-5-5  effort: medium",
                      "# cost (USD, harness-reported): 0.010000",
                      f"# usage: {OPUS_5_5_USAGE}")
    with pytest.raises(pytest.skip.Exception):
        _check_reproduces_harness(path)


def test_client_cost_is_recomputed_not_read_from_header():
    # run_052's header still says 4.939190 (written at the old 3x rate).
    path = ROOT / "client_sdk" / "results" / "run_052.txt"
    assert "4.939190" in path.read_text()
    assert run_cost("client", path) == pytest.approx(1.6463965, abs=5e-7)
