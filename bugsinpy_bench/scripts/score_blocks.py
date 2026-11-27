"""Score block-level Jev routing against the stored per-model reviews (design section 4).

No new reviews: each bug's or PR's outcome under a tier is the stored result of
that tier's model (light = Haiku 5.5 medium, standard = Sonnet 5.5 high,
deep = Opus 5.5 high), as in score_full.py.

Usage:
    .venv/bin/python bugsinpy_bench/scripts/score_blocks.py
Writes bugsinpy_bench/routing/blocks_scores.json.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from block_rules import auc, block_risk, decide, sweep  # noqa: E402
from score_full import MARTIAN_ARMS, MR, suite_rows  # noqa: E402

ROUTING = ROOT / "bugsinpy_bench" / "routing"
BLOCK_ROUTES = ROUTING / "blocks"
CACHE = ROOT / "bugsinpy_bench" / "router_inputs" / "blocks"
TIER_ARM = {"light": "haiku55_medium", "standard": "sonnet55_high", "deep": "opus55_high"}
TS = [round(i * 0.05, 2) for i in range(21)]
T_DECLARED = 0.5


def bugsinpy_outcomes() -> dict[str, dict]:
    per = json.loads((ROUTING / "full_scores.json").read_text())["bugsinpy"]["per_bug"]
    return {b["label"]: {t: dict(b[m]) for t, m in TIER_ARM.items()} for b in per}


def martian_outcomes() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for tier, arm in TIER_ARM.items():
        d = MR / MARTIAN_ARMS[arm]
        verdicts = {v["label"]: v for v in json.loads((d / "judged.json").read_text())["verdicts"]}
        cost = suite_rows(d / "suite.md")
        tail = MR / f"{MARTIAN_ARMS[arm]}_tail"
        if tail.exists():
            tcost = suite_rows(tail / "suite.md")
            for v in json.loads((tail / "judged.json").read_text())["verdicts"]:
                verdicts[v["label"]] = v
                cost[v["label"]] = tcost[v["label"]]
        for label, v in verdicts.items():
            out.setdefault(label, {})[tier] = {
                "matched_goldens": int(v["matched_goldens"]), "n_goldens": int(v["n_goldens"]),
                "matched_candidates": int(v["matched_candidates"]), "n_candidates": int(v["n_candidates"]),
                "cost_usd": cost[label]["cost_usd"]}
    return out


def opus_needed_split(outcomes: dict[str, dict]) -> tuple[list[str], list[str]]:
    """(deep found and light missed, light found) — the step-10 split."""
    pos = [lb for lb, o in outcomes.items() if o["deep"]["found"] and not o["light"]["found"]]
    neg = [lb for lb, o in outcomes.items() if o["light"]["found"]]
    return sorted(pos), sorted(neg)


def current_router_auc() -> float:
    pdeep = {}
    for f in ("routes_pilot30.json", "routes_rest70.json"):
        for r in json.loads((ROUTING / f).read_text())["routes"]:
            pdeep[r["label"]] = r["depth_probs"][2]
    pos, neg = opus_needed_split(bugsinpy_outcomes())
    return auc([pdeep[x] for x in pos], [pdeep[x] for x in neg])


def _max_complexity() -> dict[str, int]:
    from block_summaries import load_entries

    out = {}
    for e in load_entries("bugsinpy"):
        p = CACHE / f"{hashlib.sha256(e['diff'].encode()).hexdigest()}.json"
        if p.exists():
            blocks = json.loads(p.read_text())["blocks"]
            out[e["label"]] = max((b["complexity_1_10"] for b in blocks), default=0)
    return out


def _routes(name: str) -> dict[str, dict] | None:
    p = BLOCK_ROUTES / name
    return {r["label"]: r for r in json.loads(p.read_text())["routes"]} if p.exists() else None


def _martian_row(entries: dict[str, dict], outcomes: dict[str, dict], T: float) -> dict:
    mg = ng = mc = nc = 0
    cost = 0.0
    tiers = {t: 0 for t in TIER_ARM}
    for label, e in entries.items():
        tier = decide(e, T)
        tiers[tier] += 1
        o = outcomes[label][tier]
        mg += o["matched_goldens"]; ng += o["n_goldens"]
        mc += o["matched_candidates"]; nc += o["n_candidates"]
        cost += o["cost_usd"]
    r, p = (mg / ng if ng else 0.0), (mc / nc if nc else 0.0)
    return {"T": T, "matched_goldens": mg, "goldens": ng, "recall": round(r, 4), "precision": round(p, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0, "cost_usd": round(cost, 4), "tiers": tiers}


def main() -> int:
    bo = bugsinpy_outcomes()
    pos, neg = opus_needed_split(bo)
    comp = _max_complexity()
    result: dict = {"opus_needed": pos, "haiku_found_n": len(neg), "T_declared": T_DECLARED,
                    "auc": {"current_router_p_deep": round(current_router_auc(), 4)}, "bugsinpy": {}, "martian": {}}
    if all(x in comp for x in pos + neg):
        result["auc"]["haiku_max_complexity"] = round(auc([comp[x] for x in pos], [comp[x] for x in neg]), 4)
    print(f"Opus-needed {len(pos)} vs Haiku-found {len(neg)}")
    print(f"AUC current router P(deep)      {result['auc']['current_router_p_deep']:.3f}")
    if "haiku_max_complexity" in result["auc"]:
        print(f"AUC Haiku max complexity alone  {result['auc']['haiku_max_complexity']:.3f}")

    for arm in ("A", "B"):
        for p in (1, 2):
            ent = _routes(f"routes_bugsinpy_{arm}_p{p}.json")
            if not ent or len(ent) < len(bo):
                print(f"bugsinpy {arm} p{p}: missing or incomplete ({0 if not ent else len(ent)} routes)")
                continue
            risk = {lb: block_risk(e["blocks"]) for lb, e in ent.items()}
            ck3 = {lb: (e["pr"]["change_kind"] or [0, 0, 0, 1])[3] for lb, e in ent.items()}
            key = f"{arm}_p{p}"
            rows = sweep(ent, bo, TS)
            result["bugsinpy"][key] = {
                "auc_block_risk": round(auc([risk[x] for x in pos], [risk[x] for x in neg]), 4),
                "auc_change_kind_top": round(auc([ck3[x] for x in pos], [ck3[x] for x in neg]), 4),
                "at_declared_T": next(r for r in rows if r["T"] == T_DECLARED),
                "sweep": rows,
                "tiers_at_T": {lb: decide(e, T_DECLARED) for lb, e in ent.items()},
                "errors": {"blocks": sum("error" in b for e in ent.values() for b in e["blocks"]),
                           "pr": sum(e["pr"]["error"] is not None for e in ent.values())},
                "jev_calls": sum(e["jev_calls"] for e in ent.values()),
                "jev_tokens": [sum(e["jev_usage"]["input_tokens"] for e in ent.values()),
                               sum(e["jev_usage"]["output_tokens"] for e in ent.values())],
            }
            s = result["bugsinpy"][key]
            d = s["at_declared_T"]
            print(f"bugsinpy {key}: AUC block_risk {s['auc_block_risk']:.3f}  change_kind top {s['auc_change_kind_top']:.3f}"
                  f"  | T=0.5 found {d['found']} ${d['cost_usd']:.2f} tiers {d['tiers']}  errors {s['errors']}")
        a, b = result["bugsinpy"].get(f"{arm}_p1"), result["bugsinpy"].get(f"{arm}_p2")
        if a and b:
            same = sum(a["tiers_at_T"][x] == b["tiers_at_T"][x] for x in a["tiers_at_T"])
            result["bugsinpy"][f"{arm}_pass_agreement"] = round(same / len(a["tiers_at_T"]), 4)
            print(f"bugsinpy {arm} pass agreement at T=0.5: {same}/{len(a['tiers_at_T'])}")

    mo = martian_outcomes()
    for arm in ("A", "B"):
        ent = _routes(f"routes_martian_{arm}_p1.json")
        if not ent or len(ent) < len(mo):
            print(f"martian {arm}: missing or incomplete")
            continue
        rows = [_martian_row(ent, mo, T) for T in TS]
        d = next(r for r in rows if r["T"] == T_DECLARED)
        result["martian"][arm] = {"at_declared_T": d, "sweep": rows,
                                  "jev_calls": sum(e["jev_calls"] for e in ent.values())}
        print(f"martian {arm}: T=0.5 goldens {d['matched_goldens']}/{d['goldens']} F1 {d['f1']:.3f} ${d['cost_usd']:.2f} tiers {d['tiers']}")

    (ROUTING / "blocks_scores.json").write_text(json.dumps(result, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
