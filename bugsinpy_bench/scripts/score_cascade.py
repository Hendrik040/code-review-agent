"""Score the offline cascade test against the stored reviews. No new reviews.

Design, fixed before any Jev answer existed:
docs/superpowers/specs/2026-11-27-jev-review-verifier-design.md

A cascade lets `first` review every bug and adds `second` on the escalated
ones; a bug is found if either found it, and the cost is `first` on all bugs
plus `second` on the escalated ones. Jev's own cost is reported separately.

Usage:
    .venv/bin/python bugsinpy_bench/scripts/score_cascade.py
Reads bugsinpy_bench/routing/verifier/answers_*.json; writes
bugsinpy_bench/routing/cascade_scores.json.
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from block_rules import auc  # noqa: E402

ROUTING = ROOT / "bugsinpy_bench" / "routing"
ANSWERS = ROUTING / "verifier"
ARM = {"haiku": "haiku55_medium", "sonnet": "sonnet55_high", "opus": "opus55_high"}
QUESTION_IDS = ("unfiled_issue", "dismissed_as_intended", "could_not_verify")
T_DECLARED = 0.5
TS = [round(i * 0.05, 2) for i in range(1, 20)]
PAIRS = [
    ("haiku", "opus", "primary"),
    ("haiku", "sonnet", "secondary"),
    ("sonnet", "opus", "secondary"),
    ("opus", "haiku", "not a clean test: questions were written after reading these Opus traces"),
]
AUC_BAR = 0.70
RANDOM_BAR = 0.05
JEV_USD_PER_MTOK = 0.042  # input tokens; output is free (docs.typesafe.ai/models, 2026-11-27)


def load_outcomes() -> dict[str, dict]:
    per = json.loads((ROUTING / "full_scores.json").read_text())["bugsinpy"]["per_bug"]
    return {b["label"]: {arm: dict(b[model]) for arm, model in ARM.items()} for b in per}


def gain_cases(first: str, second: str, outcomes: dict[str, dict]) -> list[str]:
    """Bugs where adding `second` to `first` finds a bug `first` missed."""
    return sorted(lb for lb, o in outcomes.items() if not o[first]["found"] and o[second]["found"])


def flag_score(rec: dict, submitted: bool) -> float:
    """The largest of the three probabilities. A review that never submitted, or
    whose Jev call failed, is always worth a second look."""
    if not submitted or "error" in rec:
        return 1.0
    return max(float(rec["answers"][q]) for q in QUESTION_IDS)


def cascade(first: str, second: str, escalate: set[str], outcomes: dict[str, dict]) -> tuple[int, float]:
    found = sum(bool(o[first]["found"] or (lb in escalate and o[second]["found"])) for lb, o in outcomes.items())
    cost = sum(o[first]["cost_usd"] + (o[second]["cost_usd"] if lb in escalate else 0.0)
               for lb, o in outcomes.items())
    return found, cost


def random_share(first: str, second: str, n: int, observed_found: int, outcomes: dict[str, dict],
                 trials: int = 10000, seed: int = 0, strict: bool = False) -> float:
    """Share of random escalation sets of size n that find at least as many bugs
    as `observed_found` (strictly more with strict=True)."""
    labels = sorted(outcomes)
    gains = set(gain_cases(first, second, outcomes))
    base = cascade(first, second, set(), outcomes)[0]
    rng = random.Random(seed)
    hits = 0
    for _ in range(trials):
        found = base + sum(lb in gains for lb in rng.sample(labels, n))
        hits += (found > observed_found) if strict else (found >= observed_found)
    return hits / trials


def router_deep_set() -> set[str]:
    """The bugs the shipped router (risk 0.15) sends to the deep tier."""
    out: set[str] = set()
    for f in ("routes_pilot30.json", "routes_rest70.json"):
        out |= {r["label"] for r in json.loads((ROUTING / f).read_text())["routes"] if r["tier"] == "deep"}
    return out


def _row(first: str, second: str, escalate: set[str], outcomes: dict[str, dict]) -> dict:
    """The cascade with this escalation set, next to a random set of the same size."""
    n = len(outcomes)
    gains = set(gain_cases(first, second, outcomes))
    base_found, base_cost = cascade(first, second, set(), outcomes)
    second_total = sum(o[second]["cost_usd"] for o in outcomes.values())
    found, cost = cascade(first, second, escalate, outcomes)
    k = len(escalate)
    return {"escalated": k, "found": found, "cost_usd": round(cost, 2),
            "random_expected_found": round(base_found + len(gains) * k / n, 1),
            "random_expected_cost_usd": round(base_cost + second_total * k / n, 2),
            "gain_cases_escalated": len(gains & escalate)}


def score_pass(first: str, second: str, answers: dict[str, dict], outcomes: dict[str, dict],
               threshold: float = T_DECLARED, trials: int = 10000) -> dict:
    """Everything reported for one pass of Jev answers about `first`'s reviews.

    AUC orientation: 1.0 means every gain case (first missed, second found) has
    a higher flag than every other review of `first`; 0.5 is chance.
    """
    labels = sorted(outcomes)
    gains = set(gain_cases(first, second, outcomes))
    others = [lb for lb in labels if lb not in gains]
    flags = {lb: flag_score(answers[lb], answers[lb]["submitted"]) for lb in labels}
    escalate = {lb for lb in labels if flags[lb] >= threshold}
    row = _row(first, second, escalate, outcomes)
    q_auc = {}
    for q in QUESTION_IDS:
        v = {lb: (answers[lb]["answers"][q] if "answers" in answers[lb] else 1.0) for lb in labels}
        q_auc[q] = round(auc([v[x] for x in gains], [v[x] for x in others]), 3)
    return {
        "auc_flag": round(auc([flags[x] for x in gains], [flags[x] for x in others]), 3),
        "auc_per_question": q_auc,
        "median_flag_gain_cases": round(statistics.median(flags[x] for x in gains), 3) if gains else None,
        "median_flag_other_reviews": round(statistics.median(flags[x] for x in others), 3) if others else None,
        "escalated_labels": sorted(escalate),
        "at_declared_T": row,
        "random_share_at_least_as_good": random_share(first, second, row["escalated"], row["found"], outcomes,
                                                      trials=trials),
        "random_share_strictly_better": random_share(first, second, row["escalated"], row["found"], outcomes,
                                                     trials=trials, strict=True),
        "sweep": [{"T": T, **_row(first, second, {lb for lb in labels if flags[lb] >= T}, outcomes)} for T in TS],
    }


def meets_bar(passes: list[dict]) -> bool:
    """The success bar of the design: in every pass, an AUC of at least 0.70 and
    at most 5% of random sets of the same size finding strictly more bugs."""
    return bool(passes) and all(
        p["auc_flag"] >= AUC_BAR and p["random_share_strictly_better"] <= RANDOM_BAR for p in passes)


def _answers(arm: str, pass_: int) -> dict[str, dict] | None:
    p = ANSWERS / f"answers_{arm}_p{pass_}.json"
    return {r["label"]: r for r in json.loads(p.read_text())["reviews"]} if p.exists() else None


def _router_p_deep() -> dict[str, float]:
    out = {}
    for f in ("routes_pilot30.json", "routes_rest70.json"):
        for r in json.loads((ROUTING / f).read_text())["routes"]:
            out[r["label"]] = r["depth_probs"][2]
    return out


def main() -> int:
    outcomes = load_outcomes()
    labels = sorted(outcomes)
    p_deep = _router_p_deep()
    deep_set = router_deep_set()
    result: dict = {"T_declared": T_DECLARED, "auc_bar": AUC_BAR, "random_bar": RANDOM_BAR, "pairs": {}, "jev": {}}

    for arm in ARM:
        for p in (1, 2):
            a = _answers(arm, p)
            if a:
                tin = sum(r.get("usage", {}).get("input_tokens", 0) for r in a.values())
                result["jev"][f"{arm}_p{p}"] = {
                    "calls": len(a), "errors": sum("error" in r for r in a.values()),
                    "input_tokens": tin, "cost_usd": round(tin * JEV_USD_PER_MTOK / 1e6, 4)}

    for first, second, status in PAIRS:
        gains = set(gain_cases(first, second, outcomes))
        others = [lb for lb in labels if lb not in gains]
        base = cascade(first, second, set(), outcomes)
        missed = {lb for lb in labels if not outcomes[lb][first]["found"]}
        pair: dict = {
            "status": status, "gain_cases": len(gains),
            "first_alone": {"found": base[0], "cost_usd": round(base[1], 2)},
            "second_on_every_bug": _row(first, second, set(labels), outcomes),
            "perfect_signal": _row(first, second, missed, outcomes),
            "passes": {},
        }
        print(f"\n=== {first} first, {second} second ({status}); gain cases {len(gains)}; "
              f"{first} alone {base[0]} found ${base[1]:.2f}")
        for p in (1, 2):
            a = _answers(first, p)
            if not a or len(a) < len(labels):
                print(f"  pass {p}: answers missing or incomplete")
                continue
            rec = score_pass(first, second, a, outcomes)
            row = rec["at_declared_T"]
            pair["passes"][f"p{p}"] = rec
            print(f"  pass {p}: AUC flag {rec['auc_flag']:.3f}  per question {rec['auc_per_question']}")
            print(f"          median flag: gain cases {rec['median_flag_gain_cases']}, other reviews {rec['median_flag_other_reviews']}")
            print(f"          T=0.5: escalated {row['escalated']}, caught {row['gain_cases_escalated']}/{len(gains)} gain cases, "
                  f"found {row['found']} for ${row['cost_usd']:.2f} | random same size: {row['random_expected_found']} "
                  f"for ${row['random_expected_cost_usd']:.2f} | random sets at least as good {rec['random_share_at_least_as_good']:.3f}, "
                  f"strictly better {rec['random_share_strictly_better']:.3f}")
        recs = list(pair["passes"].values())
        if len(recs) == 2:
            same = sum((lb in recs[0]["escalated_labels"]) == (lb in recs[1]["escalated_labels"]) for lb in labels)
            pair["pass_agreement_at_T"] = round(same / len(labels), 3)
            print(f"  passes agree on {same}/{len(labels)} escalation decisions at T=0.5")

        # Baselines that need no new Jev call.
        a1 = _answers(first, 1)
        if a1 and len(a1) >= len(labels):
            nothing = {lb for lb in labels if a1[lb]["n_findings"] == 0}
            pair["baselines"] = {
                "filed_nothing": {**_row(first, second, nothing, outcomes),
                                  "auc": round(auc([float(x in nothing) for x in gains],
                                                   [float(x in nothing) for x in others]), 3)},
                "router_deep_set": _row(first, second, deep_set, outcomes),
                "fewer_turns_auc": round(auc([-a1[x]["num_turns"] for x in gains],
                                             [-a1[x]["num_turns"] for x in others]), 3),
                "router_p_deep_auc": round(auc([p_deep[x] for x in gains], [p_deep[x] for x in others]), 3),
            }
            b = pair["baselines"]
            print(f"  baselines: filed nothing AUC {b['filed_nothing']['auc']:.3f} "
                  f"(escalates {b['filed_nothing']['escalated']}, found {b['filed_nothing']['found']} for "
                  f"${b['filed_nothing']['cost_usd']:.2f}; random {b['filed_nothing']['random_expected_found']}); "
                  f"router's deep set (escalates {b['router_deep_set']['escalated']}, found {b['router_deep_set']['found']} "
                  f"for ${b['router_deep_set']['cost_usd']:.2f}; random {b['router_deep_set']['random_expected_found']}); "
                  f"fewer turns AUC {b['fewer_turns_auc']:.3f}; router P(deep) AUC {b['router_p_deep_auc']:.3f}")
        if status == "primary" and len(recs) == 2:
            pair["meets_success_bar"] = meets_bar(recs)
            print(f"  SUCCESS BAR (AUC >= {AUC_BAR} and at most {RANDOM_BAR:.0%} of random sets better, both passes): "
                  f"{'met' if pair['meets_success_bar'] else 'NOT met'}")
        result["pairs"][f"{first}_then_{second}"] = pair

    if result["jev"]:
        print("\nJev usage:", {k: (v["calls"], v["errors"], v["input_tokens"], v["cost_usd"]) for k, v in result["jev"].items()})
    (ROUTING / "cascade_scores.json").write_text(json.dumps(result, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
