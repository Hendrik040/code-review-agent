"""Merge a tail/rescue sweep into a parent sweep.

Use after a sweep capped early or was killed mid-flight: launch a
follow-up sweep on the missing bugs, then merge it back into the
parent so scoring + plotting see one unified cell.

What it does:
  - copies parent/runs/<file> + tail/runs/<file> into a single runs/
  - appends tail rows into parent's suite.md (skipping its own header)
  - updates parent's meta.json: bumps total_cost_usd, n_entries,
    and records the merge

Usage:
    uv run python bugsinpy_bench/scripts/merge_tail.py \\
        --parent bugsinpy_bench/results/sweep_2026-05-04_client_high \\
        --tail bugsinpy_bench/results/sweep_2026-05-04_client_high_tail
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parent", required=True)
    ap.add_argument("--tail", required=True)
    args = ap.parse_args()
    parent = Path(args.parent)
    tail = Path(args.tail)
    if not parent.is_dir():
        sys.exit(f"parent is not a dir: {parent}")
    if not tail.is_dir():
        sys.exit(f"tail is not a dir: {tail}")

    # Copy runs.
    p_runs = parent / "runs"
    t_runs = tail / "runs"
    p_runs.mkdir(exist_ok=True)
    copied = 0
    for f in t_runs.iterdir():
        if not f.is_file():
            continue
        dest = p_runs / f.name
        shutil.copy2(f, dest)
        copied += 1
    print(f"copied {copied} run file(s) from tail → parent")

    # Append tail's suite.md rows (skipping header).
    parent_suite = (parent / "suite.md").read_text()
    tail_suite = (tail / "suite.md").read_text()
    in_table_tail = False
    appended_rows: list[str] = []
    for line in tail_suite.splitlines():
        if line.startswith("| entry "):
            in_table_tail = True
            continue
        if in_table_tail and line.startswith("|---"):
            continue
        if in_table_tail and line.startswith("| "):
            appended_rows.append(line + "\n")
        elif in_table_tail and not line.startswith("|"):
            in_table_tail = False
    # Insert rows just before the parent's "**Summary:**" footer (if present).
    if "**Summary:**" in parent_suite:
        head, tail_section = parent_suite.split("**Summary:**", 1)
        new_suite = head.rstrip() + "\n" + "".join(appended_rows) + "\n**Summary:**" + tail_section
    else:
        new_suite = parent_suite + "".join(appended_rows)
    (parent / "suite.md").write_text(new_suite)
    print(f"appended {len(appended_rows)} row(s) to parent suite.md")

    # Update meta.json — bump n_entries, total_cost.
    p_meta = json.loads((parent / "meta.json").read_text())
    t_meta = json.loads((tail / "meta.json").read_text())
    p_meta["n_entries"] = (p_meta.get("n_entries", 0) or 0) + (t_meta.get("n_entries", 0) or 0)
    p_meta["total_cost_usd"] = round(
        (p_meta.get("total_cost_usd", 0) or 0) + (t_meta.get("total_cost_usd", 0) or 0), 4
    )
    merges = p_meta.setdefault("merged_tails", [])
    merges.append({
        "tail_sweep_id": t_meta.get("sweep_id"),
        "tail_n": t_meta.get("n_entries"),
        "tail_cost_usd": t_meta.get("total_cost_usd"),
    })
    (parent / "meta.json").write_text(json.dumps(p_meta, indent=2))
    print(f"updated parent meta: n_entries={p_meta['n_entries']}, "
          f"total_cost=${p_meta['total_cost_usd']:.2f}")
    print(f"\nmerged: {tail.name} → {parent.name}")


if __name__ == "__main__":
    main()
