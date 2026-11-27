"""Anthropic API pricing (USD per million tokens).

The module-level constants are the `claude-opus-4-7` rates: $5 input /
$25 output, cache writes at 1.25x input (5 min) and 2x input (1 h), cache
reads at 0.1x input. `cost_usd(usage)` with no model uses them; that is
what the Client SDK reviewer and the offload runners, which still run
Opus 4.7, call. The Agent SDK reviewer defaults to `claude-opus-5-5` and
can be routed to other models, so it calls `cost_usd(usage, model)`,
which prices from the per-model `RATES` table below.

The Opus 4.7 constants reproduce the harness's own `total_cost_usd`
(ResultMessage) from the stored usage dict of an Opus 4.7 run:
agent_sdk/results/run_044.txt has 8 input, 13,835
output, 179,482 cache-read and 77,307 5-minute cache-write tokens, which
is $0.918825 at these rates and $0.918825 harness-reported.

Until this was corrected the constants were the Opus 4 / 4.1 rates
($15 / $75 / $18.75 / $30 / $1.50), exactly 3x too high for Opus 4.7. Any
`# cost (USD, API rate)` or `public Opus 4 rate` line in a results/ file
written before the fix is therefore 3x the real cost; the `# usage:` line
next to it is correct, and scripts/headtohead.py and
scripts/reeval_suite.py recompute cost from it.
"""

INPUT = 5.00
OUTPUT = 25.00
CACHE_WRITE_5M = 6.25
CACHE_WRITE_1H = 10.00
CACHE_READ = 0.50


# Phase 7 — per-model rates for routed runs: (input, output, cache read)
# in USD per million tokens. Cache writes are 1.25x input (5 min) and
# 2x input (1 h) on all of these. The Opus 4.7 row reproduces the
# harness's own total_cost_usd to the cent on run_044 ($0.918825), and
# so do the module-level constants above, which hold the same rates.
# Haiku 5.5 is absent on purpose: its rate steps up past 100K prompt
# tokens, which a per-run usage total can't apply.
RATES: dict[str, tuple[float, float, float]] = {
    "claude-opus-4-7": (5.00, 25.00, 0.50),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
}


def cost_usd(usage: dict, model: str | None = None) -> float | None:
    """Compute USD cost from a usage dict (Anthropic SDK shape).

    With `model`, use that model's row in RATES and return None when
    the model isn't listed (better no number than a wrong one). Without
    it, behave exactly as before Phase 7.
    """
    if model is None:
        rates = (INPUT, OUTPUT, CACHE_READ, CACHE_WRITE_5M, CACHE_WRITE_1H)
    elif model in RATES:
        i, o, r = RATES[model]
        rates = (i, o, r, i * 1.25, i * 2.0)
    else:
        return None
    in_rate, out_rate, read_rate, cw5_rate, cw1_rate = rates
    input_t = (usage.get("input_tokens") or 0)
    output_t = (usage.get("output_tokens") or 0)
    cache_read = (usage.get("cache_read_input_tokens") or 0)
    cache_create = (usage.get("cache_creation_input_tokens") or 0)

    # Split cache writes by TTL if the API surfaced it.
    cc = usage.get("cache_creation") or {}
    cc_5m = cc.get("ephemeral_5m_input_tokens", 0) or 0
    cc_1h = cc.get("ephemeral_1h_input_tokens", 0) or 0
    if cc_5m or cc_1h:
        cw5, cw1 = cc_5m, cc_1h
    else:
        cw5, cw1 = cache_create, 0

    return (
        input_t * in_rate
        + output_t * out_rate
        + cache_read * read_rate
        + cw5 * cw5_rate
        + cw1 * cw1_rate
    ) / 1_000_000
