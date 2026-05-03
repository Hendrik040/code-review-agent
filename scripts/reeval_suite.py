"""Re-evaluate an existing suite_NNN.md against the current matcher.

When the matcher in `scripts/run_suite.py` changes (e.g. category
required for hits — CR catch on PR #20), we want to refresh the
file_hit / line_hit columns of past suites WITHOUT paying for a
full re-run. Each `<sdk>/results/run_NNN.txt` already contains the
JSON-encoded model findings; this script reads them, applies the new
matcher, and writes a new suite_NNN.md.

Usage:
    uv run python scripts/reeval_suite.py <sdk>/results/suite_NNN.md
    uv run python scripts/reeval_suite.py --line-tolerance 10 \\
        client_sdk/results/suite_002.md agent_sdk/results/suite_002.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

# Project root on path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reuse the matcher + table writer from the canonical runner so they
# stay in sync.
from scripts.run_suite import (  # noqa: E402
    _expected_match,
    _markdown_table,
)
from shared.findings import Finding  # noqa: E402
from shared.fixtures import ALL_FIXTURES  # noqa: E402

# Map suite_NNN.md row -> run_NNN.txt path.
_RUN_RE = re.compile(r"\| run_(\d+) \|")


def _load_findings(result_path: Path) -> list[Finding]:
    """Parse the JSON tail of a run_NNN.txt into Finding dataclasses."""
    blob = result_path.read_text()
    if "# ---" not in blob:
        return []
    json_part = blob.split("# ---", 1)[1].strip()
    try:
        raw = json.loads(json_part)
    except json.JSONDecodeError:
        return []
    out: list[Finding] = []
    for item in raw:
        try:
            out.append(Finding(**item))
        except (TypeError, ValueError):
            continue
    return out


def _parse_suite(suite_path: Path) -> list[dict[str, Any]]:
    """Pull (fixture, run_id, num_turns, cost, findings_count, latency,
    exit_reason) tuples out of an existing suite_NNN.md.
    """
    rows: list[dict[str, Any]] = []
    in_table = False
    for line in suite_path.read_text().splitlines():
        if line.startswith("| fixture "):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("| ") and "run_" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            # cells: fixture, turns, cost, findings, expected, file_hit,
            #        line_hit, exit, latency, run_id
            if len(cells) < 10:
                continue
            try:
                run_id = int(re.search(r"run_(\d+)", cells[9]).group(1))
            except (AttributeError, ValueError):
                run_id = None
            rows.append(
                {
                    "fixture": cells[0],
                    "num_turns": int(cells[1]),
                    "cost_usd": float(cells[2].lstrip("$")),
                    "num_findings": int(cells[3]),
                    "expected_count": int(cells[4]),
                    "exit_reason": cells[7],
                    "latency_s": float(cells[8]),
                    "run_id": run_id,
                }
            )
        elif in_table and not line.startswith("|"):
            in_table = False
    return rows


def _reeval(
    suite_path: Path,
    line_tolerance: int,
) -> str:
    sdk = "agent" if "agent_sdk" in str(suite_path) else "client"
    sdk_dir = suite_path.resolve().parent.parent  # <sdk>_sdk/
    results_dir = sdk_dir / "results"

    rows_meta = _parse_suite(suite_path)
    fixtures_by_name = {f.name: f for f in ALL_FIXTURES}

    new_rows: list[dict[str, Any]] = []
    for meta in rows_meta:
        fx = fixtures_by_name.get(meta["fixture"])
        if fx is None:
            print(f"  warning: unknown fixture {meta['fixture']!r}; skipping",
                  file=sys.stderr)
            continue
        run_path = results_dir / f"run_{meta['run_id']:03d}.txt"
        findings = _load_findings(run_path) if run_path.is_file() else []
        file_hit, line_hit = _expected_match(findings, fx.expected, line_tolerance)
        new_rows.append({**meta, "file_hit": file_hit, "line_hit": line_hit})
        print(
            f"  {fx.name:<22}"
            f"  findings={len(findings)}"
            f"  file_hit={'Y' if file_hit else 'N'}"
            f"  line_hit={'Y' if line_hit else 'N'}"
        )

    # Use a fake suite_started so wall-time stays positive but doesn't
    # imply a fresh run; we keep the original latency_s per-row as the
    # source of truth.
    suite_id_match = re.search(r"suite_(\d+)\.md$", suite_path.name)
    suite_id = int(suite_id_match.group(1)) if suite_id_match else 0
    table = _markdown_table(
        new_rows,
        line_tolerance,
        sdk,
        suite_id,
        suite_started=time.time() - sum(r["latency_s"] for r in new_rows),
        completed=True,
    )
    # Add a banner so it's clear this was re-evaluated, not re-run.
    return (
        "<!-- Re-evaluated by scripts/reeval_suite.py against the current "
        "matcher; per-run findings unchanged, file_hit / line_hit columns "
        "recomputed. -->\n\n"
    ) + table


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("suite", nargs="+", help="Path(s) to existing suite_NNN.md.")
    ap.add_argument("--line-tolerance", type=int, default=10)
    ap.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite the suite_NNN.md in place (default: print to stdout).",
    )
    args = ap.parse_args()

    for suite in args.suite:
        path = Path(suite)
        if not path.is_file():
            sys.exit(f"not a file: {path}")
        print(f"\n=== {path} ===")
        new_text = _reeval(path, args.line_tolerance)
        if args.in_place:
            path.write_text(new_text)
            print(f"  rewritten: {path}")
        else:
            print()
            print(new_text)


if __name__ == "__main__":
    main()
