"""Decision rule and scoring helpers for block-level Jev routing.

Pure functions, no I/O. The rule is fixed by
docs/superpowers/specs/2026-11-27-jev-block-routing-design.md, section 3:

- deep if P(high_stakes) >= 0.5 or block_risk >= T
- else from change_kind probs p[0..3]: light if p[2] + p[3] <= 0.15,
  standard if p[3] <= 0.15, else deep
- a missing change_kind (Jev error) routes deep, like the current router
"""

from __future__ import annotations


RISK = 0.15
HIGH_STAKES_FLOOR = 0.5
RISK_NOULS = ("precision_logic", "state_tracking", "error_path", "contract_change", "value_domain")
TIERS = ("light", "standard", "deep")


def norm_levels(raw: dict, n: int) -> list[float] | None:
    """Probabilities keyed by level (int or str) as a list of length n.
    None if they don't sum to 1 within 0.1."""
    out = [0.0] * n
    for k, v in raw.items():
        i = int(k)
        if 0 <= i < n:
            out[i] = float(v)
    return out if abs(sum(out) - 1.0) <= 0.1 else None


def _one_block_risk(block: dict) -> float:
    if "error" in block or "answers" not in block:
        return 1.0
    a = block["answers"]
    effort = a.get("verify_effort")
    if not effort:
        return 1.0
    return max([float(a[q]) for q in RISK_NOULS] + [float(effort[-1])])


def block_risk(blocks: list[dict]) -> float:
    """Max over blocks of max(P(Q1..Q5 yes), P(top level of verify_effort)).
    A block with an error counts as 1.0 (fail toward deep)."""
    return max((_one_block_risk(b) for b in blocks), default=0.0)


def decide(entry: dict, T: float) -> str:
    pr = entry["pr"]
    hs = pr.get("high_stakes")
    if hs is not None and hs >= HIGH_STAKES_FLOOR:
        return "deep"
    if block_risk(entry["blocks"]) >= T:
        return "deep"
    p = pr.get("change_kind")
    if not p:
        return "deep"
    if p[2] + p[3] <= RISK + 1e-9:
        return "light"
    if p[3] <= RISK + 1e-9:
        return "standard"
    return "deep"


def auc(pos: list[float], neg: list[float]) -> float:
    """P(a random positive scores above a random negative); ties count 0.5."""
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def sweep(entries: dict[str, dict], outcomes: dict[str, dict], Ts: list[float]) -> list[dict]:
    """Bugs found, review cost and tier counts at each threshold T."""
    rows = []
    for T in Ts:
        found, cost, tiers = 0, 0.0, {t: 0 for t in TIERS}
        for label, entry in entries.items():
            tier = decide(entry, T)
            tiers[tier] += 1
            found += bool(outcomes[label][tier]["found"])
            cost += outcomes[label][tier]["cost_usd"]
        rows.append({"T": T, "found": found, "cost_usd": round(cost, 4), "tiers": tiers})
    return rows
