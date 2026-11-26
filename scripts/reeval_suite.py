"""Re-evaluate an existing suite_NNN.md against the current matcher.

When the matcher in `scripts/run_suite.py` changes (e.g. category
required for hits — CR catch on PR #20), we want to refresh the
file_hit / line_hit columns of past suites WITHOUT paying for a
full re-run. Each `<sdk>/results/run_NNN.txt` already contains the
JSON-encoded model findings; this script reads them, applies the new
matcher, and writes a new suite_NNN.md.

The cost column is refreshed the same way: it is taken from each run's
stored header / usage (`scripts/headtohead.py:run_cost`) rather than
copied from the old suite table, so a pricing.py correction reaches
past suites without a re-run. `--cost-only` rewrites nothing but the
cost figures (per-row cost and the summary total) and leaves every
other byte of the suite file — hit columns included — as recorded.

A suite row is only re-costed from run_NNN.txt when that file still
holds the run the row describes (run ids were reused early on, so a
later run can have overwritten it). Otherwise the recorded cost is
kept and the row is named in a banner.

Usage:
    uv run python scripts/reeval_suite.py <sdk>/results/suite_NNN.md
    uv run python scripts/reeval_suite.py --line-tolerance 10 \\
        client_sdk/results/suite_002.md agent_sdk/results/suite_002.md
    uv run python scripts/reeval_suite.py --cost-only --in-place \\
        client_sdk/results/suite_*.md
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
from scripts.headtohead import run_cost  # noqa: E402
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
        # `"run_" in line` would skip rows that crashed or timed out
        # (whose `run_id` cell is `-`), corrupting re-eval totals.
        # CR's catch on PR #21. Match by leading pipe + length only;
        # rows without a numeric run_id keep run_id=None.
        if in_table and line.startswith("| ") and not line.startswith("|---"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            # cells: fixture, turns, cost, findings, expected, file_hit,
            #        line_hit, exit, latency, run_id
            if len(cells) < 10:
                continue
            m = re.search(r"run_(\d+)", cells[9])
            run_id = int(m.group(1)) if m else None
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


def _run_file_mismatch(meta: dict[str, Any], run_path: Path) -> str | None:
    """Why `run_path` is NOT the run this suite row recorded, or None.

    Compares facts that don't depend on pricing: the fixture named in the
    `# repo:` line (when it names one), the turn count and the number of
    findings.
    """
    head = run_path.read_text().partition("# ---")[0]

    def _hdr(prefix: str) -> str | None:
        for line in head.splitlines():
            if line.startswith(prefix):
                return line.split(":", 1)[1].strip()
        return None

    repo = _hdr("# repo:") or ""
    m = re.search(r"fixture-(.+)-[^-/]+$", repo)
    if m and m.group(1) != meta["fixture"]:
        return f"file holds a {m.group(1)} run"
    turns = _hdr("# turns:")
    if turns and turns.isdigit() and int(turns) != meta["num_turns"]:
        return f"file has {turns} turns, row has {meta['num_turns']}"
    found = _hdr("# findings:")
    if found and found.isdigit() and int(found) != meta["num_findings"]:
        return f"file has {found} findings, row has {meta['num_findings']}"
    return None


def _fresh_cost(
    meta: dict[str, Any], sdk: str, results_dir: Path
) -> tuple[float, str | None]:
    """(cost, problem) for one suite row.

    cost is recomputed from the run file when it can be; otherwise it is
    the recorded figure and `problem` says why it was kept.
    """
    if meta.get("run_id") is None:
        return meta["cost_usd"], None  # crashed / timed out: nothing to cost
    name = f"run_{meta['run_id']:03d}"
    run_path = results_dir / f"{name}.txt"
    if not run_path.is_file():
        return meta["cost_usd"], f"{meta['fixture']}/{name}: file missing"
    why = _run_file_mismatch(meta, run_path)
    if why:
        return meta["cost_usd"], f"{meta['fixture']}/{name}: {why}"
    cost = run_cost(sdk, run_path)
    if cost is None:
        return meta["cost_usd"], f"{meta['fixture']}/{name}: no usage in header"
    return cost, None


_KEPT_BANNER = (
    "<!-- Recorded cost kept as-is (run file no longer holds this run, so "
    "its usage can't be re-costed): {rows}. A figure recorded before the "
    "pricing.py rate correction is 3x the claude-opus-4-7 rate. -->\n\n"
)


def _recost(suite_path: Path) -> str:
    """Return the suite file's text with only its cost figures refreshed."""
    sdk = "agent" if "agent_sdk" in str(suite_path) else "client"
    results_dir = suite_path.resolve().parent
    text = suite_path.read_text()
    rows = _parse_suite(suite_path)
    by_key = {(r["fixture"], r["run_id"]): r for r in rows}

    kept: list[str] = []
    total = 0.0
    changed = False
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        row = None
        if line.startswith("| ") and len(cells) >= 10:
            m = re.search(r"run_(\d+)", cells[9])
            row = by_key.get((cells[0], int(m.group(1)) if m else None))
        if row is not None:
            cost, problem = _fresh_cost(row, sdk, results_dir)
            if problem:
                kept.append(problem)
            total += cost
            new_cell = f"${cost:.4f}"
            print(f"  {row['fixture']:<22}  {cells[2]} -> {new_cell}"
                  + (f"  (kept: {problem})" if problem else ""))
            if new_cell != cells[2]:
                changed = True
                # The cost cell is the third "|"-delimited field.
                parts = line.split("|")
                parts[3] = parts[3].replace(cells[2], new_cell)
                line = "|".join(parts)
        elif "total cost $" in line:
            line = re.sub(
                r"total cost \$[0-9.]*[0-9]", f"total cost ${total:.4f}", line
            )
        out.append(line)

    body = "".join(out)
    if not changed and not kept:
        return text
    banner = ""
    if changed:
        banner += (
            "<!-- Cost figures recomputed by scripts/reeval_suite.py "
            "--cost-only from each run's stored usage at the current "
            "pricing.py rate; nothing else in this file was changed. "
            "-->\n\n"
        )
    if kept and "Recorded cost kept as-is" not in text:
        banner += _KEPT_BANNER.format(rows="; ".join(kept))
    return banner + body


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
        # Crashed / timed-out rows have run_id=None; skip the result-
        # file load and treat findings as empty so the row still
        # contributes to the re-eval totals (with file_hit/line_hit
        # = False for non-empty `expected`). CR's catch on PR #21.
        if meta.get("run_id") is None:
            findings: list[Finding] = []
        else:
            run_path = results_dir / f"run_{meta['run_id']:03d}.txt"
            findings = _load_findings(run_path) if run_path.is_file() else []
        file_hit, line_hit = _expected_match(findings, fx.expected, line_tolerance)
        cost, problem = _fresh_cost(meta, sdk, results_dir)
        if problem:
            print(f"  warning: cost kept as recorded — {problem}",
                  file=sys.stderr)
        meta = {**meta, "cost_usd": cost}
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
    ap.add_argument(
        "--cost-only",
        action="store_true",
        help="Refresh only the cost figures; leave everything else, "
             "including the hit columns, exactly as recorded.",
    )
    args = ap.parse_args()

    for suite in args.suite:
        path = Path(suite)
        if not path.is_file():
            sys.exit(f"not a file: {path}")
        print(f"\n=== {path} ===")
        if args.cost_only:
            new_text = _recost(path)
        else:
            new_text = _reeval(path, args.line_tolerance)
        if args.in_place:
            path.write_text(new_text)
            print(f"  rewritten: {path}")
        else:
            print()
            print(new_text)


if __name__ == "__main__":
    main()
