"""Context size and token use per review, before vs after Jev impact selection.

For every affected entry (bench_impact/affected.json) and model, read the
reviewer trace of the baseline run and of the impact-selection rerun and
record: chars returned by build_review_context (None when it returned the
"exceeds maximum allowed tokens" error), whether it errored, the run's total
tokens (in + cache write + cache read + out), cost and judge-found.
Also records the size the old context would have had (affected.json:
diff + every candidate in full) so overflowed runs still have a "before" size.

Usage: .venv/bin/python bench_impact/plots/measure_context.py --traces-before DIR
Writes bench_impact/plots/context_tokens.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench_impact"))
import score_impact as si  # noqa: E402

TOTALS = re.compile(r"totals: in=(\d+) cache_w=(\d+) cache_r=(\d+) out=(\d+)")


def trace_facts(trace_dir: Path, rid: int | None) -> dict | None:
    if rid is None:
        return None
    p = trace_dir / f"run_{rid:03d}.txt"
    if not p.exists():
        return None
    t = p.read_text(errors="ignore")
    i = t.find("for: mcp__reviewer__build_review_context")
    m = re.search(r"chars: ([\d,]+)", t[i:i + 400]) if i >= 0 else None
    err = si.ctx_error(trace_dir, rid)
    tot = TOTALS.search(t)
    head = re.sub(r"[\s│]+", " ", t[i:i + 1200]) if i >= 0 else ""
    big = re.search(r"result \(([\d,]+) characters", head)
    kb = re.search(r"Output too large \(([\d.]+)KB\)", head)
    shown = int(m.group(1).replace(",", "")) if m else None
    # how the reviewer got the context: inline (all of it), preview (Claude Code
    # saved it to a file and showed a 2 KB preview) or error (too large to save inline)
    status = "error" if err else "preview" if kb else "inline"
    full = int(big.group(1).replace(",", "")) if big else round(float(kb.group(1)) * 1024) if kb else shown
    return {"status": status, "full_chars": full, "shown_chars": None if err else shown,
            "ctx_chars": None if err or not m else shown,
            "ctx_error": bool(err),
            "tokens": sum(map(int, tot.groups())) if tot else None,
            "fresh_tokens": int(tot.group(1)) + int(tot.group(2)) + int(tot.group(4)) if tot else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces-before", type=Path, required=True)
    a = ap.parse_args()
    new = ROOT / "agent_sdk" / "traces"
    affected = json.loads((ROOT / "bench_impact" / "affected.json").read_text())
    old_size = {}
    for k, v in affected.items():
        if v.get("affected"):
            src, lab = k.split(":", 1)
            lab = lab if src == "bugsinpy" else si.pr_label(lab)
            old_size[lab] = v["diff_chars"] + v["impact_chars"]
    rows = []
    for m in si.MODELS:
        arms = {
            "before": (sorted((si.BASE / "bugsinpy").glob(f"sweep_*_{m}_*")) + [si.BASE / "martian" / f"sweep_2026-11-27_martian_{m}"], a.traces_before),
            "after": ([si.NEW_B / f"sweep_2026-11-27_impactsel_{m}_aff16", si.NEW_M / f"sweep_2026-11-27_impactsel_martian_{m}_aff6"], new),
        }
        found = {"before": {}, "after": {}}
        b_b = si.bugsinpy_arm(arms["before"][0][:-1], a.traces_before)
        a_b = si.bugsinpy_arm(arms["after"][0][:1], new)
        for arm, sweeps, traces, data in (("before", arms["before"][0], a.traces_before, b_b), ("after", arms["after"][0], new, a_b)):
            ids = {}
            for s in sweeps:
                if s.exists():
                    ids.update(si.run_ids(s))
            for lab in old_size:
                f = trace_facts(traces, ids.get(lab))
                if f is None:
                    continue
                rows.append({"model": m, "arm": arm, "label": lab, "would_be_chars": old_size[lab],
                             "found": data.get(lab, {}).get("found"), **f})
    out = ROOT / "bench_impact" / "plots" / "context_tokens.json"
    out.write_text(json.dumps(rows, indent=1) + "\n")
    print(len(rows), "rows ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
