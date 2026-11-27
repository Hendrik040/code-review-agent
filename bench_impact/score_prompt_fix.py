"""Score the prompt-fix test (bench_impact/run_prompt_fix.sh).

Ten bugs whose context overflowed before impact selection; Sonnet 5.5 high and
Opus 5.5 high; arms old (IMPACT_SELECT=off), new (jev), verify (jev + the
REVIEW_PROMPT_VARIANT=verify prompt); two repetitions each. Also pools in the
earlier runs of the same bugs: the baseline sweeps as "old" and the
impactsel aff16 sweeps (plus Opus rep2) as "new". Checks that every trace ran
with the intended prompt and that only the old arm hit the context error.

Usage: .venv/bin/python bench_impact/score_prompt_fix.py --traces-before DIR
Writes bench_impact/prompt_fix_scores.json.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from score_impact import bugsinpy_arm, run_ids

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "bugsinpy_bench" / "results"
TR = ROOT / "agent_sdk" / "traces"
MODELS = ("sonnet55_high", "opus55_high")
ARMS = ("old", "new", "verify")
BUGS = sorted(f"{e['project']}#{e['bug_id']}" for e in json.loads((ROOT / "bench_impact/prepared_ctxerr10.json").read_text()))


def trace_stats(sweep: Path, traces: Path) -> dict[str, dict]:
    out = {}
    for lb, rid in run_ids(sweep).items():
        t = (traces / f"run_{rid:03d}.txt").read_text(errors="ignore")
        m = re.search(r"findings=(\d+)", t)
        out[lb] = {"tools": t.count("tool_use:"), "findings": int(m.group(1)) if m else 0,
                   "verify_prompt": "trimmed selection" in t, "run": rid}
    return out


def arm_runs(model: str, arm: str, traces_before: Path) -> list[dict]:
    runs = []
    for rep in (1, 2):
        s = RES / f"sweep_2026-11-27_promptfix_{model}_{arm}_r{rep}"
        runs.append({"source": s.name, "fresh": True, "sweep": s, "traces": TR})
    if arm == "old":
        for s in sorted((ROOT / "bench_impact/baseline/bugsinpy").glob(f"sweep_*_{model}_*")):
            runs.append({"source": s.name, "fresh": False, "sweep": s, "traces": traces_before, "group": "baseline"})
    if arm == "new":
        prev = [RES / f"sweep_2026-11-27_impactsel_{model}_aff16"]
        if model == "opus55_high":
            prev.append(RES / "sweep_2026-11-27_impactsel_opus55_high_aff16_rep2")
        for s in prev:
            runs.append({"source": s.name, "fresh": False, "sweep": s, "traces": TR})
    return runs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces-before", type=Path, required=True)
    a = ap.parse_args()
    out = {"bugs": BUGS, "models": {}}
    problems = []
    for m in MODELS:
        out["models"][m] = {}
        for arm in ARMS:
            runs = arm_runs(m, arm, a.traces_before)
            # The baseline is split over two sweeps (pilot30 + rest70): merge them into one run.
            base = [r for r in runs if r.get("group") == "baseline"]
            merged = [r for r in runs if r.get("group") != "baseline"]
            if base:
                merged.append({"source": "+".join(r["source"] for r in base), "fresh": False,
                               "sweeps": [r["sweep"] for r in base], "traces": a.traces_before})
            reps = []
            for r in merged:
                sweeps = r.get("sweeps") or [r["sweep"]]
                res = bugsinpy_arm(sweeps, r["traces"])
                st = {}
                for s in sweeps:
                    st.update(trace_stats(s, r["traces"]))
                rows = {lb: {**res[lb], **st[lb]} for lb in BUGS}
                for lb, x in rows.items():
                    if x["verify_prompt"] != (arm == "verify"):
                        problems.append(f"{m} {arm} {r['source']} {lb}: wrong prompt")
                    if bool(x["ctx_error"]) != (arm == "old"):
                        problems.append(f"{m} {arm} {r['source']} {lb}: ctx_error={x['ctx_error']}")
                reps.append({"source": r["source"], "fresh": r["fresh"],
                             "found": sum(x["found"] for x in rows.values()),
                             "cost_usd": round(sum(x["cost_usd"] for x in rows.values()), 4),
                             "tools": sum(x["tools"] for x in rows.values()),
                             "findings": sum(x["findings"] for x in rows.values()),
                             "ctx_errors": sum(bool(x["ctx_error"]) for x in rows.values()),
                             "per_bug": {lb: x["found"] for lb, x in rows.items()}})
            out["models"][m][arm] = reps
    out["problems"] = problems
    (ROOT / "bench_impact/prompt_fix_scores.json").write_text(json.dumps(out, indent=1) + "\n")
    for m in MODELS:
        print(m)
        for arm in ARMS:
            for r in out["models"][m][arm]:
                tag = "fresh" if r["fresh"] else "earlier"
                print(f"  {arm:6s} {tag:7s} found {r['found']:2d}/10 ${r['cost_usd']:5.2f} tools {r['tools']:3d} findings {r['findings']:2d} ctxerr {r['ctx_errors']:2d}  {r['source']}")
        print("  per bug (found count over all runs of the arm):")
        for lb in BUGS:
            cells = "  ".join(f"{arm} {sum(r['per_bug'][lb] for r in out['models'][m][arm])}/{len(out['models'][m][arm])}" for arm in ARMS)
            print(f"    {lb:12s} {cells}")
    print("problems:", problems or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
