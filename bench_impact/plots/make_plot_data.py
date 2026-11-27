"""Collect the numbers the plots page draws into bench_impact/plots/data.json.

Reads bench_impact/impact_scores.json (run score_impact.py first) and adds,
per affected bug and model, the reviewer's tool calls and cost before and
after, from the sweeps' run files and Agent SDK traces.

Usage: .venv/bin/python bench_impact/plots/make_plot_data.py --traces-before DIR
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench_impact"))
from score_impact import MODELS, run_ids, suite_costs  # noqa: E402


def per_bug(sweeps: list[Path], traces: Path) -> dict[str, dict]:
    out = {}
    for s in sweeps:
        cost = suite_costs(s / "suite.md")
        for lb, rid in run_ids(s).items():
            p = traces / f"run_{rid:03d}.txt"
            t = p.read_text(errors="ignore") if p.exists() else ""
            m = re.search(r"findings=(\d+)", t)
            out[lb] = {"tools": t.count("tool_use:"), "cost": cost.get(lb),
                       "findings": int(m.group(1)) if m else None}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces-before", type=Path, required=True)
    a = ap.parse_args()
    scores = json.loads((ROOT / "bench_impact" / "impact_scores.json").read_text())
    aff = scores["bugsinpy"]["affected_reviewed"]
    detail = {}
    for m in MODELS:
        b = per_bug(sorted((ROOT / "bench_impact/baseline/bugsinpy").glob(f"sweep_*_{m}_*")), a.traces_before)
        n = per_bug([ROOT / f"bugsinpy_bench/results/sweep_2026-11-27_impactsel_{m}_aff16"], ROOT / "agent_sdk/traces")
        detail[m] = {lb: {"before": b[lb], "after": n[lb]} for lb in aff}
    out = {"scores": scores, "affected_detail": detail}
    (ROOT / "bench_impact/plots/data.json").write_text(json.dumps(out, indent=1) + "\n")
    print("wrote bench_impact/plots/data.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
