"""Pre-sample a fixed N-bug subset of prepared.json for matrix runs.

We want every cell in the (SDK × effort) matrix to score against the
EXACT SAME bugs — otherwise we can't compare cells. This script does a
stratified random sample by project (proportional to project size) and
writes the result to prepared_<N>.json. All matrix runs use that file.

Stratified rather than uniform random because uniform-random over 172
entries would heavily over-weight pandas/scrapy/keras (the big-3) and
under-represent the long-tail projects (PySnooper, sanic, cookiecutter,
etc.). Stratified-proportional preserves the actual blame-yield
distribution while guaranteeing every project that had any blame
entries is represented.

Usage:
    uv run python bugsinpy_bench/scripts/sample_dataset.py \\
        --n 100 --seed 42 \\
        --input  bugsinpy_bench/dataset/prepared.json \\
        --output bugsinpy_bench/dataset/prepared_100.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--source", default="blame",
                    help="Which source(s) to sample from (default: blame).")
    args = ap.parse_args()

    raw = json.loads(Path(args.input).read_text())
    sources = {s.strip() for s in args.source.split(",") if s.strip()}
    pool = [e for e in raw if e["source"] in sources]
    if not pool:
        sys.exit(f"no entries with source in {sources}")

    by_project: dict[str, list] = defaultdict(list)
    for e in pool:
        by_project[e["project"]].append(e)

    n_total = len(pool)
    target = min(args.n, n_total)
    if target < args.n:
        print(f"warning: requested {args.n} but only {n_total} runnable; capping",
              file=sys.stderr)

    # Proportional allocation with largest-remainder rounding.
    raw_alloc = {p: target * len(es) / n_total for p, es in by_project.items()}
    floor_alloc = {p: int(v) for p, v in raw_alloc.items()}
    remaining = target - sum(floor_alloc.values())
    # Distribute the remainder to projects with the largest fractional parts.
    fractional = sorted(
        ((raw_alloc[p] - floor_alloc[p], p) for p in floor_alloc),
        reverse=True,
    )
    for _, p in fractional[:remaining]:
        floor_alloc[p] += 1
    # Cap at the project's actual size (can't sample more than exists).
    for p in floor_alloc:
        floor_alloc[p] = min(floor_alloc[p], len(by_project[p]))

    rng = random.Random(args.seed)
    picked: list = []
    for project, n_p in sorted(floor_alloc.items()):
        if n_p == 0:
            continue
        picked.extend(rng.sample(by_project[project], n_p))

    # Sort for deterministic ordering — every cell sees bugs in the same order.
    picked.sort(key=lambda e: (e["project"], e["bug_id"]))

    Path(args.output).write_text(json.dumps(picked, indent=2))

    # Report.
    by_p = Counter(e["project"] for e in picked)
    print(f"Sampled {len(picked)} bugs from {n_total} {sources}-source entries "
          f"in {args.input} (seed={args.seed}).")
    print("Per-project distribution:")
    for p, n in sorted(by_p.items(), key=lambda kv: -kv[1]):
        total = len(by_project[p])
        print(f"  {p:<14}  {n:>3} / {total:>3} ({100*n/total:.0f}%)")
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    main()
