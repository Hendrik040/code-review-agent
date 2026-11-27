"""Full-benchmark comparison of three setups on Sonnet 5.5 high and Opus 5.5 high.

  old     today's context (baseline sweeps, bench_impact/baseline/)
  new     Jev impact selection (baseline, with the 16 affected bugs replaced by
          the impactsel aff16 runs; on the other 84 the context is identical)
  verify  Jev impact selection + REVIEW_PROMPT_VARIANT=verify: the verify
          sweeps over 90 bugs (first pass, before the API credit ran out, plus
          the _resume pass) and promptfix verify r1 for the other 10 (r2 as a
          second estimate)

Bugs a sweep did not review (cost cap) are left out of every setup's count, so
all three are compared on the same bugs. Martian: micro recall / precision / F1
over the PRs every setup reviewed.

Usage: .venv/bin/python bench_impact/score_verify_full.py --traces-before DIR
Writes bench_impact/verify_full_scores.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from score_impact import bugsinpy_arm, martian_arm, micro, suite_costs

ROOT = Path(__file__).resolve().parent.parent
RB, RM, BASE = ROOT / "bugsinpy_bench/results", ROOT / "martian_bench/results", ROOT / "bench_impact/baseline"
TR = ROOT / "agent_sdk/traces"
MODELS = ("sonnet55_high", "opus55_high")


def paid(rows: dict, sweeps: list[Path]) -> dict:
    """Drop entries that crashed at $0 (the first pass ran out of API credit)."""
    ok = set()
    for s in sweeps:
        ok |= {k for k, v in suite_costs(s / "suite.md").items() if v > 0}
    return {k: v for k, v in rows.items() if k in ok}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces-before", type=Path, required=True)
    a = ap.parse_args()
    out = {"bugsinpy": {}, "martian": {}}
    for m in MODELS:
        old = bugsinpy_arm(sorted((BASE / "bugsinpy").glob(f"sweep_*_{m}_*")), a.traces_before)
        aff = bugsinpy_arm([RB / f"sweep_2026-11-27_impactsel_{m}_aff16"], TR)
        new = {**old, **aff}
        vs = [RB / f"sweep_2026-11-27_verify_{m}_rest90", RB / f"sweep_2026-11-27_verify_{m}_rest90_resume"]
        v90 = paid(bugsinpy_arm(vs, TR), vs)
        estimates = {}
        for rep in ("r1", "r2"):
            v10 = bugsinpy_arm([RB / f"sweep_2026-11-27_promptfix_{m}_verify_{rep}"], TR)
            estimates[rep] = {**v90, **v10}
        common = sorted(set(estimates["r1"]) & set(old))
        def tot(d):
            rows = [d[k] for k in common]
            return {"found": sum(r["found"] for r in rows), "of": len(rows),
                    "cost_usd": round(sum(r["cost_usd"] for r in rows), 2),
                    "ctx_errors": sum(bool(r["ctx_error"]) for r in rows)}
        unchanged = [k for k in common if k not in aff]
        out["bugsinpy"][m] = {
            "missing": sorted(set(old) - set(common)),
            "old": tot(old), "new": tot(new),
            "verify_r1": tot(estimates["r1"]), "verify_r2": tot(estimates["r2"]),
            "unchanged_context": {  # 84 bugs whose context is the same: prompt effect alone
                "n": len(unchanged),
                "old_found": sum(old[k]["found"] for k in unchanged),
                "verify_found": sum(estimates["r1"][k]["found"] for k in unchanged),
                "gained": sorted(k for k in unchanged if estimates["r1"][k]["found"] and not old[k]["found"]),
                "lost": sorted(k for k in unchanged if old[k]["found"] and not estimates["r1"][k]["found"]),
            },
        }
        # findings and judged-real counts (precision proxy)
        def judged(sweeps):
            d = {}
            for s in sweeps:
                for v in json.loads((s / "judged.json").read_text())["verdicts"]:
                    d[v["label"]] = (v["findings_count"], v["real_count"])
            return d
        jo = judged(sorted((BASE / "bugsinpy").glob(f"sweep_*_{m}_*")))
        jv = judged(vs + [RB / f"sweep_2026-11-27_promptfix_{m}_verify_r1"])
        out["bugsinpy"][m]["findings_real"] = {
            "old": [sum(jo[k][0] for k in common), sum(jo[k][1] for k in common)],
            "verify": [sum(jv[k][0] for k in common), sum(jv[k][1] for k in common)]}

        mb = martian_arm(BASE / f"martian/sweep_2026-11-27_martian_{m}", a.traces_before)
        maff = martian_arm(RM / f"sweep_2026-11-27_impactsel_martian_{m}_aff6", TR)
        mnew = {**mb, **maff}
        mvs = [RM / f"sweep_2026-11-27_verify_martian_{m}", RM / f"sweep_2026-11-27_verify_martian_{m}_resume"]
        mv = {}
        for s in mvs:
            mv.update(paid(martian_arm(s, TR), [s]))
        mc = sorted(set(mv) & set(mb))
        out["martian"][m] = {"prs": len(mc), "missing": sorted(set(mb) - set(mc)),
                             **{k: micro({lb: d[lb] for lb in mc}) for k, d in (("old", mb), ("new", mnew), ("verify", mv))}}
    (ROOT / "bench_impact/verify_full_scores.json").write_text(json.dumps(out, indent=1) + "\n")
    for m in MODELS:
        b = out["bugsinpy"][m]
        print(f"{m}  BugsInPy on {b['old']['of']} bugs (missing {b['missing']})")
        for k in ("old", "new", "verify_r1", "verify_r2"):
            print(f"   {k:10s} found {b[k]['found']:3d}  ${b[k]['cost_usd']:6.2f}  ctx errors {b[k]['ctx_errors']}")
        u = b["unchanged_context"]
        print(f"   unchanged-context bugs ({u['n']}): old {u['old_found']} -> verify {u['verify_found']}  gained {u['gained']} lost {u['lost']}")
        print(f"   findings/real old {b['findings_real']['old']} verify {b['findings_real']['verify']}")
        mm = out["martian"][m]
        print(f"   Martian on {mm['prs']} PRs (missing {mm['missing']})")
        for k in ("old", "new", "verify"):
            s = mm[k]
            print(f"     {k:7s} R {s['recall']:.3f} P {s['precision']:.3f} F1 {s['f1']:.3f} ${s['cost_usd']:.2f} ctx errors {s['ctx_errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
