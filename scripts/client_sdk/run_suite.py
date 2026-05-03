"""Run the Client SDK reviewer across all registered fixtures.

Sweeps `shared.fixtures.ALL_FIXTURES`, materializes each into a temp
git repo, calls `client_sdk.reviewer.run()`, and tabulates:

  cost_usd, num_turns, findings (count), expected hit (file match),
  expected hit (file + within +/- N lines), exit_reason, latency_s

Output goes to:
  - stdout (markdown table)
  - client_sdk/results/suite_NNN.md (same table, persisted)
  - the per-run trace/result files written by reviewer.run() itself

Usage:
    uv run python scripts/client_sdk/run_suite.py
    uv run python scripts/client_sdk/run_suite.py --fixtures sentry_80168,contract_mismatch
    uv run python scripts/client_sdk/run_suite.py --line-tolerance 20
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

# Project root on path so `shared.*` and `client_sdk.*` resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from client_sdk import reviewer
from shared.findings import Finding
from shared.fixtures import ALL_FIXTURES, Fixture, materialize

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "client_sdk" / "results"
DEFAULT_LINE_TOLERANCE = 10


def _next_suite_id() -> int:
    RESULTS_DIR.mkdir(exist_ok=True)
    used = [
        int(m.group(1))
        for p in RESULTS_DIR.glob("suite_*.md")
        if (m := re.match(r"suite_(\d+)\.md$", p.name))
    ]
    return (max(used) + 1) if used else 1


def _expected_match(
    findings: list[Finding],
    expected: list[Finding],
    line_tolerance: int,
) -> tuple[bool, bool]:
    """Two-tier match check.

    Returns (file_hit, line_hit):
      file_hit  — at least one model finding hits the same file as
                  *any* expected finding. Coarse: tells us the agent
                  was in the right neighborhood.
      line_hit  — model finding hits the same file AND its line is
                  within +/- line_tolerance of an expected line. The
                  stricter signal.
    """
    if not expected:
        # No expected finding registered — nothing to match against.
        # Treat empty model output as "fine", non-empty as "noise".
        return (not findings, not findings)

    expected_files = {f.file for f in expected}
    file_hit = any(f.file in expected_files for f in findings)

    line_hit = any(
        f.file == e.file and abs(f.line - e.line) <= line_tolerance
        for f in findings
        for e in expected
    )
    return file_hit, line_hit


def _run_one(
    fx: Fixture,
    line_tolerance: int,
) -> dict:
    print(f"\n=== {fx.name} ===", flush=True)
    started = time.time()
    with materialize(fx) as materialized:
        result = reviewer.run(
            materialized.repo_path,
            materialized.base_ref,
            materialized.head_ref,
        )
    elapsed = time.time() - started

    file_hit, line_hit = _expected_match(
        result["findings"], fx.expected, line_tolerance
    )

    print(
        f"  turns={result['num_turns']:>2}  "
        f"cost=${result['cost_usd']:.4f}  "
        f"findings={len(result['findings'])}  "
        f"expected_file={'Y' if file_hit else 'N'}  "
        f"expected_line+/-{line_tolerance}={'Y' if line_hit else 'N'}  "
        f"exit={result['exit_reason']}  "
        f"latency={elapsed:.1f}s",
        flush=True,
    )

    return {
        "fixture": fx.name,
        "run_id": result["run_id"],
        "num_turns": result["num_turns"],
        "cost_usd": result["cost_usd"],
        "num_findings": len(result["findings"]),
        "expected_count": len(fx.expected),
        "file_hit": file_hit,
        "line_hit": line_hit,
        "exit_reason": result["exit_reason"],
        "latency_s": elapsed,
        "trace_path": result["trace_path"],
    }


def _markdown_table(rows: list[dict], line_tolerance: int) -> str:
    header = (
        f"| fixture | turns | cost (USD) | findings | expected | "
        f"file hit | line +/-{line_tolerance} | exit | latency (s) | run_id |\n"
        f"|---|---:|---:|---:|---:|:---:|:---:|---|---:|---:|\n"
    )
    body = "\n".join(
        f"| {r['fixture']} | {r['num_turns']} | "
        f"${r['cost_usd']:.4f} | {r['num_findings']} | "
        f"{r['expected_count']} | "
        f"{'Y' if r['file_hit'] else 'N'} | "
        f"{'Y' if r['line_hit'] else 'N'} | "
        f"{r['exit_reason']} | {r['latency_s']:.1f} | "
        f"run_{r['run_id']:03d} |"
        for r in rows
    )
    total_cost = sum(r["cost_usd"] for r in rows)
    total_turns = sum(r["num_turns"] for r in rows)
    file_hits = sum(1 for r in rows if r["file_hit"])
    line_hits = sum(1 for r in rows if r["line_hit"])
    n = len(rows)
    summary = (
        f"\n\n**Summary:** {n} fixtures, total cost ${total_cost:.4f}, "
        f"total turns {total_turns}, file-hit {file_hits}/{n}, "
        f"line-hit {line_hits}/{n}.\n"
    )
    return header + body + summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Sweep Client SDK reviewer over fixtures.")
    ap.add_argument(
        "--fixtures",
        default="",
        help="Comma-separated fixture names (default: all registered).",
    )
    ap.add_argument(
        "--line-tolerance",
        type=int,
        default=DEFAULT_LINE_TOLERANCE,
        help=f"+/- N lines for the line-match column (default: {DEFAULT_LINE_TOLERANCE}).",
    )
    args = ap.parse_args()

    if args.fixtures:
        wanted = {n.strip() for n in args.fixtures.split(",") if n.strip()}
        selected = [f for f in ALL_FIXTURES if f.name in wanted]
        missing = wanted - {f.name for f in selected}
        if missing:
            sys.exit(f"unknown fixtures: {sorted(missing)}")
    else:
        selected = list(ALL_FIXTURES)

    print(f"Sweeping {len(selected)} fixture(s): {[f.name for f in selected]}")

    rows: list[dict] = []
    suite_started = time.time()
    for fx in selected:
        rows.append(_run_one(fx, args.line_tolerance))
    suite_elapsed = time.time() - suite_started

    table = _markdown_table(rows, args.line_tolerance)
    print("\n" + table)
    print(f"\nSuite wall time: {suite_elapsed:.1f}s")

    suite_id = _next_suite_id()
    suite_path = RESULTS_DIR / f"suite_{suite_id:03d}.md"
    suite_path.write_text(
        f"# Client SDK reviewer suite run {suite_id:03d}\n\n"
        f"Wall time: {suite_elapsed:.1f}s. Line tolerance: +/- {args.line_tolerance}.\n\n"
        + table
    )
    print(f"Saved: {suite_path}")


if __name__ == "__main__":
    main()
