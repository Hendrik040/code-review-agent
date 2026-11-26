"""Anthropic API pricing for Claude Opus 4.7 (USD per million tokens).

These are the rates the reviewers' model, `claude-opus-4-7`, is billed at:
$5 input / $25 output, cache writes at 1.25x input (5 min) and 2x input
(1 h), cache reads at 0.1x input.

They reproduce the harness's own `total_cost_usd` (ResultMessage) from the
stored usage dict: agent_sdk/results/run_044.txt has 8 input, 13,835
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


def cost_usd(usage: dict) -> float:
    """Compute USD cost from a usage dict (Anthropic SDK shape)."""
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
        input_t * INPUT
        + output_t * OUTPUT
        + cache_read * CACHE_READ
        + cw5 * CACHE_WRITE_5M
        + cw1 * CACHE_WRITE_1H
    ) / 1_000_000
