"""Anthropic API pricing for Claude Opus 4.x (USD per million tokens).

Numbers are from Anthropic's published pricing for Claude Opus 4. They line up
with the harness's own `total_cost_usd` field on ResultMessage (verified
empirically: a $1.099 run at the published rates matches the harness output).
"""

INPUT = 15.00
OUTPUT = 75.00
CACHE_WRITE_5M = 18.75
CACHE_WRITE_1H = 30.00
CACHE_READ = 1.50


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
