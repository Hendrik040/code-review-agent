"""Martian scores when several stored reviews of the same PR are merged.

No new reviews and no judge calls: reads the stored judge verdicts. A golden
comment counts as matched if any merged review matched it. Findings are pooled
without removing duplicates, so precision is matched findings over all
findings of the merged reviews. A sweep's `_tail` rerun replaces its failed
rows, as in bugsinpy_bench/scripts/score_full.py.

Usage:
    python3 martian_bench/scripts/merge_scores.py
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"
ARMS = {
    "haiku": "sweep_2026-11-27_martian_haiku55_medium",
    "sonnet": "sweep_2026-11-27_martian_sonnet55_high",
    "opus": "sweep_2026-11-27_martian_opus55_high",
    "opus_file_considered": "sweep_2026-11-27_martian_opus55_high_fileconsidered",
    "sonnet_file_considered": "sweep_2026-11-27_martian_sonnet55_high_fileconsidered",
}
SETUPS = (["haiku"], ["sonnet"], ["opus"], ["opus_file_considered"], ["haiku", "sonnet"], ["haiku", "opus"],
          ["haiku", "opus_file_considered"], ["haiku", "sonnet", "opus"])


def _verdicts(sweep: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in (sweep, f"{sweep}_tail"):
        p = RESULTS / d / "judged.json"
        if p.exists():
            for v in json.loads(p.read_text())["verdicts"]:
                out[v["label"]] = v
    return out


def _cost(sweep: str) -> float:
    rows: dict[str, float] = {}
    for d in (sweep, f"{sweep}_tail"):
        p = RESULTS / d / "suite.md"
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            c = [x.strip() for x in line.split("|")]
            if len(c) > 6 and "#" in c[1] and c[1] != "pr":
                rows[c[1]] = float(next(x for x in c[2:] if x.startswith("$")).lstrip("$"))
    return sum(rows.values())


def _pairs(v: dict) -> list[dict]:
    return ast.literal_eval(v["pairs"]) if isinstance(v["pairs"], str) else v["pairs"]


def merged(arms: list[str]) -> dict:
    verdicts = {a: _verdicts(ARMS[a]) for a in arms}
    goldens = of = findings = matched_findings = 0
    for label in verdicts[arms[0]]:
        hit: set[int] = set()
        for a in arms:
            v = verdicts[a][label]
            hit |= {p["golden_idx"] for p in _pairs(v) if p["match"]}
            findings += int(v["n_candidates"])
            matched_findings += int(v["matched_candidates"])
        goldens += len(hit)
        of += int(verdicts[arms[0]][label]["n_goldens"])
    recall = goldens / of if of else 0.0
    precision = matched_findings / findings if findings else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"arms": arms, "goldens": goldens, "of": of, "findings": findings,
            "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "cost_usd": round(sum(_cost(ARMS[a]) for a in arms), 2)}


def main() -> int:
    print(f"{'setup':40s} goldens findings precision    F1   cost")
    for arms in SETUPS:
        m = merged(list(arms))
        print(f"{' + '.join(arms):40s} {m['goldens']:3d}/{m['of']:<3d} {m['findings']:8d} {m['precision']:9.3f} "
              f"{m['f1']:5.3f} ${m['cost_usd']:5.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
