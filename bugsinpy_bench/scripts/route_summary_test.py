"""Does a Haiku summary of the change help the router? (offline test)

DESIGN, fixed and committed before any Jev call of this test:

- Two arms through the same code path, both built from the stored diffs
  (bugsinpy_bench/router_inputs/<bug>.diff):
    control  the router's own state: title, per-file line counts, the diff cut
             at 24,000 characters (the text shared/routing.py::build_state makes)
    summary  the same state plus one section after the title: a heading saying
             it is a description written by another model that does not judge
             the change, then what_changed and the four lists of the stored
             Haiku summary (router_inputs/<bug>.summary.json)
- Same two questions (QUESTIONS of shared/routing.py at 3e69e01), same rule
  (risk_replay.tier_at, which is routing.pick_level), risk 0.15.
- Two passes per arm, because Jev's answers vary between calls. One Jev call
  per bug per arm per pass: 400 calls.
- Scored on the stored reviews in routing/full_scores.json. No new reviews.
- Success bar: in BOTH passes the summary arm finds at least as many bugs as the
  control arm of the same pass at risk 0.15 AND costs less, AND its P(deep)
  ranks the 8 bugs "Opus found, Sonnet missed" above the other bugs better than
  control does (higher AUC). Anything else is reported as "no measurable gain".
- Also reported: each arm against the logged original routing (42 found,
  $14.15), the replay at every risk in risk_replay.RISKS, how many bugs change
  tier between arms and between passes, and Jev's tokens and cost.

Known limits: one review run per model per bug, 100 bugs, so a difference of
one or two bugs is noise. The summaries describe non-test Python files only.

Usage:
    .venv/bin/python bugsinpy_bench/scripts/route_summary_test.py run --arm control --pass 1
    .venv/bin/python bugsinpy_bench/scripts/route_summary_test.py score
Writes routing/summary_test/answers_{arm}_p{pass}.json and summary_test/scores.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from block_rules import auc  # noqa: E402
from block_summaries import numstat  # noqa: E402
from risk_replay import RISKS, TIER_ARM, tier_at  # noqa: E402

ROUTING = ROOT / "bugsinpy_bench" / "routing"
OUT = ROUTING / "summary_test"
INPUTS = ROOT / "bugsinpy_bench" / "router_inputs"
ARMS = ("control", "summary")
MAX_DIFF_CHARS = 24_000
RISK = 0.15
JEV_USD_PER_MTOK = 0.042
SUMMARY_HEADING = ("Description of the change, written by another model. "
                   "It describes what changed and does not judge it:")
LISTS = (("behavior_before_after", "Behavior before and after"), ("interfaces_touched", "Interfaces touched"),
         ("data_touched", "Data touched"), ("error_handling_changes", "Error handling changes"))


def base_state(title: str, diff: str, max_chars: int = MAX_DIFF_CHARS) -> str:
    """The text shared/routing.py::build_state sends, rebuilt from a stored diff."""
    stat = "\n".join(f"{f['added']}\t{f['removed']}\t{f['path']}" for f in numstat(diff))
    shown = diff[:max_chars]
    cut = f" (first {len(shown)} of {len(diff)} characters)" if len(shown) < len(diff) else ""
    parts = [f"Pull request title: {title}" if title else "",
             "Files changed (lines added, lines removed, path):", stat, f"Diff{cut}:", shown]
    return "\n".join(p for p in parts if p)


def summary_section(summary: dict) -> str:
    lines = [SUMMARY_HEADING, summary.get("what_changed") or "(no non-test Python file changed)"]
    for key, label in LISTS:
        if summary.get(key):
            lines.append(f"{label}:")
            lines += [f"- {item}" for item in summary[key]]
    return "\n".join(lines)


def state_for(arm: str, title: str, diff: str, summary: dict) -> str:
    state = base_state(title, diff)
    if arm == "control":
        return state
    if arm != "summary":
        raise ValueError(f"unknown arm {arm!r}")
    marker = "Files changed (lines added, lines removed, path):"
    head, rest = state.split(marker, 1)
    return head + summary_section(summary) + "\n" + marker + rest


def ask(state: str, questions: dict, client) -> dict:
    try:
        resp = client.system_one(state=state, questions=questions)
        raw = resp.answers["depth"].probabilities
        probs = [float(raw.get(i, raw.get(str(i), 0.0))) for i in range(len(questions["depth"]["criteria"]))]
        if abs(sum(probs) - 1.0) > 0.1:
            raise ValueError("depth probabilities do not sum to 1")
        return {"depth_probs": probs, "high_stakes": float(resp.answers["high_stakes"].noul),
                "input_tokens": int(getattr(resp.usage, "input_tokens", 0) or 0)}
    except Exception as e:  # noqa: BLE001 — recorded; an error routes deep, as in the router
        return {"error": type(e).__name__}


def score_answers(answers: dict[str, dict], bugs: dict[str, dict], risk: float) -> dict:
    tiers = {lb: tier_at(a, risk) for lb, a in answers.items()}
    counts = {t: sum(v == t for v in tiers.values()) for t in TIER_ARM}
    found = sum(bool(bugs[lb][TIER_ARM[t]]["found"]) for lb, t in tiers.items())
    cost = sum(bugs[lb][TIER_ARM[t]]["cost_usd"] for lb, t in tiers.items())
    return {"risk": risk, "tiers": counts, "found": found, "cost_usd": round(cost, 2), "tier_of": tiers}


def _bugs() -> dict[str, dict]:
    return {b["label"]: b for b in json.loads((ROUTING / "full_scores.json").read_text())["bugsinpy"]["per_bug"]}


def _answers(arm: str, p: int) -> dict[str, dict] | None:
    f = OUT / f"answers_{arm}_p{p}.json"
    return {r["label"]: r for r in json.loads(f.read_text())["answers"]} if f.exists() else None


def run(arm: str, pass_: int, workers: int) -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    from block_summaries import load_entries
    from route_and_score import load_router

    questions = load_router().QUESTIONS
    entries = load_entries("bugsinpy")
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"answers_{arm}_p{pass_}.json"
    done = _answers(arm, pass_) or {}
    local, lock = threading.local(), threading.Lock()

    def client():
        if not hasattr(local, "c"):
            local.c = TypeSafeClient(timeout=20, retry=RetryPolicy(max_retries=1))
        return local.c

    def one(e: dict) -> None:
        stem = e["label"].replace("#", "_")
        summary = json.loads((INPUTS / f"{stem}.summary.json").read_text())
        state = state_for(arm, e["title"], e["diff"], summary)
        rec = {"label": e["label"], "state_chars": len(state), **ask(state, questions, client())}
        with lock:
            done[e["label"]] = rec
            out.write_text(json.dumps({"arm": arm, "pass": pass_, "questions": questions,
                                       "answers": sorted(done.values(), key=lambda r: r["label"])}, indent=1) + "\n")

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, [e for e in entries if e["label"] not in done]))
    rs = list(done.values())
    print(f"{arm} p{pass_}: answers={len(rs)} errors={sum('error' in r for r in rs)} "
          f"jev_in={sum(r.get('input_tokens', 0) for r in rs)}")
    return 0


def score() -> int:
    bugs = _bugs()
    labels = sorted(bugs)
    pos = [lb for lb in labels if bugs[lb]["opus55_high"]["found"] and not bugs[lb]["sonnet55_high"]["found"]]
    neg = [lb for lb in labels if lb not in pos]
    result: dict = {"risk": RISK, "opus_found_sonnet_missed": pos, "arms": {}}
    runs = {}
    for arm in ARMS:
        for p in (1, 2):
            a = _answers(arm, p)
            if not a or len(a) < len(labels):
                print(f"{arm} p{p}: missing or incomplete")
                continue
            pd = {lb: (a[lb]["depth_probs"][2] if "depth_probs" in a[lb] else 1.0) for lb in labels}
            s = score_answers(a, bugs, RISK)
            tin = sum(r.get("input_tokens", 0) for r in a.values())
            rec = {**{k: s[k] for k in ("tiers", "found", "cost_usd")},
                   "auc_p_deep": round(auc([pd[x] for x in pos], [pd[x] for x in neg]), 3),
                   "errors": sum("error" in r for r in a.values()),
                   "jev_input_tokens": tin, "jev_cost_usd": round(tin * JEV_USD_PER_MTOK / 1e6, 4),
                   "replay": [{k: v for k, v in score_answers(a, bugs, r).items() if k != "tier_of"} for r in RISKS]}
            result["arms"][f"{arm}_p{p}"] = rec
            runs[(arm, p)] = s["tier_of"]
            print(f"{arm:8s} p{p}: tiers {rec['tiers']} found {rec['found']} ${rec['cost_usd']:.2f} "
                  f"AUC P(deep) {rec['auc_p_deep']:.3f} errors {rec['errors']} jev ${rec['jev_cost_usd']}")

    def moved(x, y):
        return sum(runs[x][lb] != runs[y][lb] for lb in labels)

    if len(runs) == 4:
        result["tier_changes"] = {
            "control_p1_vs_p2": moved(("control", 1), ("control", 2)),
            "summary_p1_vs_p2": moved(("summary", 1), ("summary", 2)),
            "control_vs_summary_p1": moved(("control", 1), ("summary", 1)),
            "control_vs_summary_p2": moved(("control", 2), ("summary", 2))}
        ok = all(result["arms"][f"summary_p{p}"]["found"] >= result["arms"][f"control_p{p}"]["found"]
                 and result["arms"][f"summary_p{p}"]["cost_usd"] < result["arms"][f"control_p{p}"]["cost_usd"]
                 and result["arms"][f"summary_p{p}"]["auc_p_deep"] > result["arms"][f"control_p{p}"]["auc_p_deep"]
                 for p in (1, 2))
        result["meets_success_bar"] = ok
        print("tier changes:", result["tier_changes"])
        print("SUCCESS BAR:", "met" if ok else "NOT met")
        for r in RISKS:
            row = [next(x for x in result["arms"][f"{arm}_p{p}"]["replay"] if x["risk"] == r)
                   for arm in ARMS for p in (1, 2)]
            print(f"  risk {r:.2f}: " + " | ".join(f"{x['found']} ${x['cost_usd']:.2f}" for x in row))
    (OUT / "scores.json").write_text(json.dumps(result, indent=1) + "\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--arm", required=True, choices=ARMS)
    r.add_argument("--pass", dest="pass_", required=True, type=int, choices=[1, 2])
    r.add_argument("--workers", type=int, default=6)
    sub.add_parser("score")
    args = ap.parse_args()
    return run(args.arm, args.pass_, args.workers) if args.cmd == "run" else score()


if __name__ == "__main__":
    raise SystemExit(main())
