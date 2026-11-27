"""Full-benchmark scores: every single-model arm and Jev triage, on BugsInPy (100) and Martian (10).

BugsInPy: the pilot sweeps (30 bugs) plus the rest-70 sweeps make each 2026-11 arm
cover all 100 bugs. Opus 4.7 comes from the stored May sweeps. Triage takes, per bug,
the stored result of the tier Jev routed it to (light = Haiku 5.5 medium,
standard = Sonnet 5.5 high, deep = Opus 5.5 high), using the committed routes in
bugsinpy_bench/routing/.

Martian: micro recall / precision / F1 over the 10 PRs as judge_martian.py computes
them. Where a sweep has a `_tail` rerun of failed PRs, the tail's verdict and cost
replace the failed row. Jev routed all 10 PRs deep, so triage there equals
all-Opus 5.5 high.

Usage:
    uv run python bugsinpy_bench/scripts/score_full.py
Writes bugsinpy_bench/routing/full_scores.json.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BR = ROOT / "bugsinpy_bench" / "results"
MR = ROOT / "martian_bench" / "results"
ROUTING = ROOT / "bugsinpy_bench" / "routing"

BUGSINPY_ARMS = {
    "haiku55_medium": ["sweep_2026-11-26_haiku55_medium_pilot30", "sweep_2026-11-27_haiku55_medium_rest70"],
    "sonnet55_high": ["sweep_2026-11-26_sonnet55_high_pilot30", "sweep_2026-11-27_sonnet55_high_rest70"],
    "opus55_high": ["sweep_2026-11-27_opus55_high_pilot30", "sweep_2026-11-27_opus55_high_rest70"],
    "opus47_low": ["sweep_2026-05-04_agent_low"],
    "opus47_high": ["sweep_2026-05-04_agent_high"],
    "opus47_max": ["sweep_2026-05-04_agent_max"],
}
TIER_ARM = {"light": "haiku55_medium", "standard": "sonnet55_high", "deep": "opus55_high"}

MARTIAN_ARMS = {
    "haiku55_medium": "sweep_2026-11-27_martian_haiku55_medium",
    "sonnet55_high": "sweep_2026-11-27_martian_sonnet55_high",
    "opus55_high": "sweep_2026-11-27_martian_opus55_high",
    "opus47_max_may": "sweep_2026-05-04_martian_agent_max",
}


def suite_rows(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text().splitlines():
        c = [x.strip() for x in line.split("|")]
        if len(c) > 6 and "#" in c[1] and c[1] != "entry":
            cost = next(x for x in c[2:] if x.startswith("$"))
            rows[c[1]] = {"cost_usd": float(cost.lstrip("$")), "exit": next(
                (x for x in c if x in ("submit_findings", "error", "timeout", "max_turns", "no_submit")), "")}
    return rows


def bugsinpy() -> dict:
    per = {}
    for arm, sweeps in BUGSINPY_ARMS.items():
        res = {}
        for s in sweeps:
            cost = suite_rows(BR / s / "suite.md")
            for v in json.loads((BR / s / "judged.json").read_text())["verdicts"]:
                res[v["label"]] = {"found": bool(v["target_recall"]), "cost_usd": cost[v["label"]]["cost_usd"]}
        per[arm] = res
    routes = {}
    for f in ("routes_pilot30.json", "routes_rest70.json"):
        for r in json.loads((ROUTING / f).read_text())["routes"]:
            routes[r["label"]] = r["tier"]
    labels = sorted(routes)
    assert all(set(labels) <= set(per[a]) for a in per), "an arm is missing bugs"

    def total(pick) -> dict:
        return {"found": sum(per[pick(lb)][lb]["found"] for lb in labels), "of": len(labels),
                "cost_usd": round(sum(per[pick(lb)][lb]["cost_usd"] for lb in labels), 4)}

    setups = {f"all_{a}": total(lambda lb, a=a: a) for a in per}
    setups["triage_jev"] = total(lambda lb: TIER_ARM[routes[lb]])
    found_by = {a: sorted(lb for lb in labels if per[a][lb]["found"]) for a in per}
    return {
        "n_bugs": len(labels),
        "tier_counts": {t: sum(1 for lb in labels if routes[lb] == t) for t in TIER_ARM},
        "setups": setups,
        "found_by": found_by,
        "per_bug": [{"label": lb, "tier": routes[lb], **{a: per[a][lb] for a in per}} for lb in labels],
    }


def martian() -> dict:
    out = {}
    for arm, sweep in MARTIAN_ARMS.items():
        d = MR / sweep
        verdicts = {v["label"]: v for v in json.loads((d / "judged.json").read_text())["verdicts"]}
        cost = suite_rows(d / "suite.md")
        tail = MR / f"{sweep}_tail"
        replaced = []
        if tail.exists():
            tcost = suite_rows(tail / "suite.md")
            for v in json.loads((tail / "judged.json").read_text())["verdicts"]:
                verdicts[v["label"]] = v
                cost[v["label"]] = tcost[v["label"]]
                replaced.append(v["label"])
        g = sum(v["n_goldens"] for v in verdicts.values())
        mg = sum(v["matched_goldens"] for v in verdicts.values())
        c = sum(v["n_candidates"] for v in verdicts.values())
        mc = sum(v["matched_candidates"] for v in verdicts.values())
        r, p = mg / g if g else 0.0, mc / c if c else 0.0
        out[arm] = {
            "prs": len(verdicts), "goldens": g, "matched_goldens": mg, "candidates": c,
            "matched_candidates": mc, "recall": round(r, 4), "precision": round(p, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
            "cost_usd": round(sum(x["cost_usd"] for x in cost.values()), 4),
            "replaced_from_tail": replaced,
            "exits": sorted({x["exit"] for x in cost.values()}),
        }
    out["triage_jev"] = dict(out["opus55_high"], note="Jev routed all 10 PRs deep")
    return out


def main() -> int:
    result = {"bugsinpy": bugsinpy(), "martian": martian()}
    (ROUTING / "full_scores.json").write_text(json.dumps(result, indent=2) + "\n")
    b = result["bugsinpy"]
    print("BugsInPy", b["n_bugs"], "bugs, routes", b["tier_counts"])
    for k, s in b["setups"].items():
        print(f"  {k:22s} found {s['found']:3d}/{s['of']}  ${s['cost_usd']:8.2f}  ${s['cost_usd']/s['of']:.4f}/bug")
    print("Martian")
    for k, s in result["martian"].items():
        print(f"  {k:22s} R {s['recall']:.3f} P {s['precision']:.3f} F1 {s['f1']:.3f}  ${s['cost_usd']:.2f}  tail {s['replaced_from_tail']} exits {s['exits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
