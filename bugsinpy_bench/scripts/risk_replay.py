"""Replay the current router's stored Jev answers at other risk settings.

No Jev calls and no reviews: the depth probabilities and the high-stakes
probability of all 100 BugsInPy bugs are in routing/routes_pilot30.json and
routes_rest70.json, and each bug's result and cost under each model is in
routing/full_scores.json. `tier_at` is the rule of shared/routing.py
(pick_level) with the risk as a parameter.

Also prints how repeatable a single model's per-bug result is, from the two
runs of Haiku 5.5 and Sonnet 5.5 on the 30 pilot bugs (routing/triage_scores.json).

Usage:
    python3 bugsinpy_bench/scripts/risk_replay.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

ROUTING = Path(__file__).resolve().parent.parent / "routing"
TIER_ARM = {"light": "haiku55_medium", "standard": "sonnet55_high", "deep": "opus55_high"}
HIGH_STAKES_FLOOR = 0.5
RISKS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90)


def tier_at(route: dict, risk: float) -> str:
    p = route.get("depth_probs") or []
    if len(p) != 3 or (route.get("high_stakes") or 0.0) >= HIGH_STAKES_FLOOR:
        return "deep"
    if p[1] + p[2] <= risk + 1e-9:
        return "light"
    if p[2] <= risk + 1e-9:
        return "standard"
    return "deep"


def _load() -> tuple[dict[str, dict], dict[str, dict]]:
    bugs = {b["label"]: b for b in json.loads((ROUTING / "full_scores.json").read_text())["bugsinpy"]["per_bug"]}
    routes = {}
    for f in ("routes_pilot30.json", "routes_rest70.json"):
        for r in json.loads((ROUTING / f).read_text())["routes"]:
            routes[r["label"]] = r
    return bugs, routes


def replay(risk: float, trials: int = 10000, seed: int = 0) -> dict:
    """Bugs found and review cost at this risk setting, and how random routing
    with the same number of bugs per tier compares."""
    bugs, routes = _load()
    labels = sorted(bugs)
    tiers = [tier_at(routes[lb], risk) for lb in labels]
    found = sum(bugs[lb][TIER_ARM[t]]["found"] for lb, t in zip(labels, tiers))
    cost = sum(bugs[lb][TIER_ARM[t]]["cost_usd"] for lb, t in zip(labels, tiers))
    counts = {t: tiers.count(t) for t in TIER_ARM}
    n = len(labels)
    expected = sum(counts[t] * sum(bugs[lb][m]["found"] for lb in labels) / n for t, m in TIER_ARM.items())
    rng = random.Random(seed)
    hits = 0
    for _ in range(trials):
        shuffled = tiers[:]
        rng.shuffle(shuffled)
        hits += sum(bugs[lb][TIER_ARM[t]]["found"] for lb, t in zip(labels, shuffled)) >= found
    all_deep = sum(bugs[lb][TIER_ARM["deep"]]["cost_usd"] for lb in labels)
    return {"risk": risk, "tiers": counts, "found": found, "cost_usd": round(cost, 2),
            "saving_vs_all_deep": round(1 - cost / all_deep, 3),
            "random_expected_found": round(expected, 1),
            "random_share_at_least_as_good": hits / trials}


def repeat_runs() -> dict:
    """The same model run twice on the 30 pilot bugs (local run and cloud rerun)."""
    pilot = json.loads((ROUTING / "triage_scores.json").read_text())["per_bug"]
    out: dict = {}
    for m in ("haiku", "sonnet"):
        a = [b[f"{m}_local"]["found"] for b in pilot]
        c = [b[f"{m}_cloud"]["found"] for b in pilot]
        out[m] = {"run1": sum(a), "run2": sum(c), "disagree": sum(x != y for x, y in zip(a, c)),
                  "merged": sum(x or y for x, y in zip(a, c))}
    bugs, _ = _load()
    needed = {lb for lb, b in bugs.items() if b["opus55_high"]["found"] and not b["haiku55_medium"]["found"]}
    in_pilot = [b for b in pilot if b["label"] in needed]
    out["opus_needed_with_second_haiku_run"] = {
        "bugs": len(in_pilot), "found_by_second_haiku_run": sum(b["haiku_cloud"]["found"] for b in in_pilot)}
    return out


def main() -> int:
    print("risk  Haiku Sonnet Opus | found  cost   saving | random same mix: expected found, share at least as good")
    for risk in RISKS:
        r = replay(risk)
        t = r["tiers"]
        print(f"{risk:4.2f}  {t['light']:5d} {t['standard']:6d} {t['deep']:4d} | {r['found']:5d} ${r['cost_usd']:6.2f} "
              f"{r['saving_vs_all_deep']:6.0%} | {r['random_expected_found']:5.1f}  {r['random_share_at_least_as_good']:.3f}")
    print("\nrepeat runs on the 30 pilot bugs:", json.dumps(repeat_runs()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
