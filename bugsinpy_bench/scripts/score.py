"""Score a BugsInPy bench sweep.

Reads bugsinpy_bench/results/<sweep_id>/{meta.json, suite.md, judged.json}
and emits a single scores.json summarizing the sweep across the agreed
metric inventory:

  Recall:
    target_recall    — bugs caught (judge: ≥1 finding matches maintainer)
    broad_recall     — bugs caught (judge: ≥1 finding is a real bug,
                       even if not the maintainer's target)
    file_recall_strict, line_recall_strict — deterministic file/line
                       matchers, kept as a sanity-check baseline

  Precision (per-finding judge verdicts):
    precision_strict     — fraction of findings that match the maintainer
    precision_plausible  — fraction of findings that are real bugs

  F1 = 2 * P_strict * R_target / (P_strict + R_target)

  Cost & latency:
    total / avg / median / p95 cost per bug
    avg / p50 / p95 latency per bug
    cost_per_target_bug = total_cost / matched_bug_count
    cost_per_real_bug   = total_cost / real_bug_count

  Behavioral:
    avg_findings_per_bug  (noise rate)
    avg_turns_per_bug
    findings_per_dollar

  Breakdowns:
    by_project — same metrics, split per project
    by_source  — same metrics, split per source (blame / synthetic)

Usage:
    uv run python bugsinpy_bench/scripts/score.py \\
        bugsinpy_bench/results/sweep_2026-05-04_agent_low
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_ROW_RE = re.compile(r"^\| ")


@dataclass
class Row:
    label: str
    project: str
    bug_id: int
    source: str
    sdk: str
    effort: str
    num_turns: int
    cost_usd: float
    num_findings: int
    file_hit_strict: bool
    line_hit_strict: bool
    target_recall: bool   # filled from judged.json
    broad_recall: bool    # filled from judged.json
    matches_count: int
    real_count: int
    exit_reason: str
    latency_s: float


def _parse_label(label: str) -> tuple[str, int]:
    project, _, bug_str = label.partition("#")
    return project.strip(), int(bug_str.strip())


def _parse_suite(suite_path: Path, sdk: str, effort: str) -> dict[str, Row]:
    rows: dict[str, Row] = {}
    in_table = False
    for line in suite_path.read_text().splitlines():
        if line.startswith("| entry "):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and _ROW_RE.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 10:
                continue
            label = cells[0]
            try:
                project, bug_id = _parse_label(label)
            except (ValueError, IndexError):
                continue
            try:
                rows[label] = Row(
                    label=label,
                    project=project,
                    bug_id=bug_id,
                    source=cells[1],
                    sdk=sdk,
                    effort=effort,
                    num_turns=int(cells[2]),
                    cost_usd=float(cells[3].lstrip("$")),
                    num_findings=int(cells[4]),
                    file_hit_strict=cells[5] == "Y",
                    line_hit_strict=cells[6] == "Y",
                    target_recall=False,
                    broad_recall=False,
                    matches_count=0,
                    real_count=0,
                    exit_reason=cells[7],
                    latency_s=float(cells[8]),
                )
            except ValueError:
                continue
        elif in_table and not line.startswith("|"):
            in_table = False
    return rows


def _merge_judge(rows: dict[str, Row], judged: dict[str, Any]) -> None:
    by_label = {v["label"]: v for v in judged.get("verdicts", [])}
    for label, row in rows.items():
        v = by_label.get(label)
        if v is None:
            continue
        row.target_recall = bool(v.get("target_recall", False))
        row.broad_recall = bool(v.get("broad_recall", False))
        row.matches_count = int(v.get("matches_count", 0))
        row.real_count = int(v.get("real_count", 0))


def _aggregate(rows: list[Row]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    file_hits = sum(1 for r in rows if r.file_hit_strict)
    line_hits = sum(1 for r in rows if r.line_hit_strict)
    target = sum(1 for r in rows if r.target_recall)
    broad = sum(1 for r in rows if r.broad_recall)
    total_findings = sum(r.num_findings for r in rows)
    total_matches = sum(r.matches_count for r in rows)
    total_real = sum(r.real_count for r in rows)
    total_cost = sum(r.cost_usd for r in rows)
    costs = sorted(r.cost_usd for r in rows)
    latencies = sorted(r.latency_s for r in rows)

    def _pct(n_hit: int) -> float:
        return round(n_hit / n, 4)

    def _safe_div(a: float, b: float) -> Optional[float]:
        return round(a / b, 4) if b else None

    p_strict = _safe_div(total_matches, total_findings)
    p_plaus = _safe_div(total_real, total_findings)
    target_recall = _pct(target)
    f1_strict = (
        round(2 * p_strict * target_recall / (p_strict + target_recall), 4)
        if (p_strict and target_recall and (p_strict + target_recall) > 0)
        else 0.0
    )

    return {
        "n": n,
        # Recall
        "target_recall": target_recall,
        "broad_recall": _pct(broad),
        "file_recall_strict": _pct(file_hits),
        "line_recall_strict": _pct(line_hits),
        "target_hits": target,
        "broad_hits": broad,
        # Precision
        "precision_strict": p_strict,
        "precision_plausible": p_plaus,
        # F1
        "f1_strict": f1_strict,
        # Counts
        "total_findings": total_findings,
        "total_matches": total_matches,
        "total_real": total_real,
        "avg_findings": round(total_findings / n, 2),
        # Cost
        "total_cost_usd": round(total_cost, 4),
        "avg_cost_usd": round(total_cost / n, 4),
        "median_cost_usd": round(statistics.median(costs), 4),
        "p95_cost_usd": round(costs[int(0.95 * (n - 1))], 4) if n else 0.0,
        "cost_per_target_bug": round(total_cost / target, 4) if target else None,
        "cost_per_real_bug": round(total_cost / broad, 4) if broad else None,
        "findings_per_dollar": round(total_findings / total_cost, 2) if total_cost else None,
        # Latency
        "avg_latency_s": round(statistics.mean(r.latency_s for r in rows), 1),
        "median_latency_s": round(statistics.median(latencies), 1),
        "p95_latency_s": round(latencies[int(0.95 * (n - 1))], 1) if n else 0.0,
        # Behavioral
        "avg_turns": round(statistics.mean(r.num_turns for r in rows), 1),
    }


def _score_sweep(sweep_dir: Path) -> dict[str, Any]:
    meta = json.loads((sweep_dir / "meta.json").read_text())
    suite_path = sweep_dir / "suite.md"
    if not suite_path.is_file():
        sys.exit(f"missing suite.md in {sweep_dir}")
    rows = _parse_suite(suite_path, meta["sdk"], meta["effort"])

    judged_path = sweep_dir / "judged.json"
    if judged_path.is_file():
        _merge_judge(rows, json.loads(judged_path.read_text()))
    else:
        print(f"  warning: judged.json not found — recall metrics will be 0",
              file=sys.stderr)

    rows_list = list(rows.values())
    by_project: dict[str, list[Row]] = defaultdict(list)
    by_source: dict[str, list[Row]] = defaultdict(list)
    for r in rows_list:
        by_project[r.project].append(r)
        by_source[r.source].append(r)

    summary = {
        "sweep_id": meta.get("sweep_id"),
        "sdk": meta.get("sdk"),
        "effort": meta.get("effort"),
        "model": meta.get("model"),
        "branch": meta.get("branch"),
        "harness_git_rev": meta.get("harness_git_rev"),
        "prepared_sha256_16": meta.get("prepared_sha256_16"),
        "global": _aggregate(rows_list),
        "by_project": {p: _aggregate(rs) for p, rs in sorted(by_project.items())},
        "by_source": {s: _aggregate(rs) for s, rs in sorted(by_source.items())},
    }
    out_path = sweep_dir / "scores.json"
    out_path.write_text(json.dumps(summary, indent=2))

    g = summary["global"]
    print(f"\n{'=' * 70}")
    print(f"Sweep: {sweep_dir.name}  (sdk={meta['sdk']} effort={meta['effort']})")
    print(f"  Model: {meta['model']}    Branch: {meta['branch']}")
    print(f"  Harness rev: {meta['harness_git_rev']}")
    print(f"  N: {g['n']}    Total cost: ${g['total_cost_usd']:.2f}")
    print(f"{'-' * 70}")
    print(f"  RECALL")
    print(f"    target (matches maintainer):    {g['target_recall']:.1%}  ({g['target_hits']}/{g['n']})")
    print(f"    broad  (any real bug):          {g['broad_recall']:.1%}  ({g['broad_hits']}/{g['n']})")
    print(f"    file_strict / line±10_strict:   {g['file_recall_strict']:.1%} / {g['line_recall_strict']:.1%}")
    if g.get("precision_strict") is not None:
        print(f"  PRECISION")
        print(f"    strict (matches/findings):      {g['precision_strict']:.1%}")
        print(f"    plausible (real/findings):      {g['precision_plausible']:.1%}")
        print(f"  F1 (strict): {g['f1_strict']:.1%}")
    print(f"  COST")
    print(f"    avg/median/p95: ${g['avg_cost_usd']:.2f} / ${g['median_cost_usd']:.2f} / ${g['p95_cost_usd']:.2f}")
    if g.get("cost_per_target_bug"):
        print(f"    per target-recall bug:          ${g['cost_per_target_bug']:.2f}")
    print(f"  LATENCY (s)")
    print(f"    avg/median/p95: {g['avg_latency_s']:.1f} / {g['median_latency_s']:.1f} / {g['p95_latency_s']:.1f}")
    print(f"  BEHAVIOR")
    print(f"    avg findings/bug: {g['avg_findings']}    avg turns: {g['avg_turns']}")

    print(f"{'-' * 70}")
    print("BY PROJECT (target_recall · cost · n):")
    for proj, agg in summary["by_project"].items():
        if agg["n"] == 0:
            continue
        print(f"  {proj:<14}  n={agg['n']:>3}  recall={agg['target_recall']:.0%}  "
              f"cost=${agg['avg_cost_usd']:.2f}/bug")

    print(f"\nWrote: {out_path}")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sweep", help="Path to sweep_<id>/ directory")
    args = ap.parse_args()
    p = Path(args.sweep)
    if not p.is_dir():
        sys.exit(f"not a directory: {p}")
    _score_sweep(p)


if __name__ == "__main__":
    main()
