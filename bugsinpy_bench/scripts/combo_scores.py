"""Score alternative routing setups on BugsInPy from stored results, with no new reviews.

Reads bugsinpy_bench/routing/full_scores.json (written by score_full.py). A setup
picks one or more models per bug; a bug counts as found if any picked model found
it, and the cost is the sum of the picked models' stored costs. Merging findings
from several models adds false positives, which BugsInPy's target recall does not
penalise.

Usage:
    python3 bugsinpy_bench/scripts/combo_scores.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
H, S, O = "haiku55_medium", "sonnet55_high", "opus55_high"
TIER = {"light": [H], "standard": [S], "deep": [O]}

SETUPS = {
    "Jev triage (as run)": lambda b: TIER[b["tier"]],
    "Jev triage + Haiku second pass on every bug": lambda b: list(dict.fromkeys(TIER[b["tier"]] + [H])),
    "Haiku everywhere + Opus 5.5 on deep only": lambda b: [H] + ([O] if b["tier"] == "deep" else []),
    "Haiku on light+standard, Opus 5.5 on deep": lambda b: [O] if b["tier"] == "deep" else [H],
    "Haiku + Opus 5.5 on every bug": lambda b: [H, O],
    "All three on every bug": lambda b: [H, S, O],
}


def main() -> int:
    bugs = json.loads((ROOT / "bugsinpy_bench" / "routing" / "full_scores.json").read_text())["bugsinpy"]["per_bug"]
    for name, pick in SETUPS.items():
        found = sum(any(b[m]["found"] for m in pick(b)) for b in bugs)
        cost = sum(b[m]["cost_usd"] for b in bugs for m in pick(b))
        print(f"{name:45s} {found:3d}/{len(bugs)}  ${cost:6.2f}")
    print("\nTriage misses that another model found:")
    for b in bugs:
        own = TIER[b["tier"]][0]
        others = [m for m in (H, S, O) if m != own and b[m]["found"]]
        if not b[own]["found"] and others:
            print(f"  {b['label']:12s} routed {b['tier']:8s} found by {', '.join(others)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
