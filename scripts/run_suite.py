"""SDK-agnostic fixture suite runner.

Sweeps `shared.fixtures.ALL_FIXTURES`, materializes each into a temp
git repo, and drives the chosen reviewer's `run()` against it. Tabulates
per-fixture cost / turns / findings / expected-match.

This is the single-SDK validation runner — the literal Client-vs-Agent
comparison harness is `compare.py --task review` (Phase 3.1).

Output:
  - stdout (markdown table)
  - <sdk>/results/suite_NNN.md (same table, persisted incrementally so
    a crash mid-sweep still leaves the partial results on disk)
  - the per-run trace/result files written by reviewer.run() itself

Usage:
    uv run python scripts/run_suite.py --sdk client
    uv run python scripts/run_suite.py --sdk agent
    uv run python scripts/run_suite.py --sdk agent --fixtures sentry_80168,contract_mismatch
    uv run python scripts/run_suite.py --sdk agent --max-cost 25 --fixture-timeout 1800

Robustness:
  - Per-fixture try/except: one crash does NOT abort the sweep. The
    crashed fixture lands in the table with `exit=error` and the
    traceback in the trace file.
  - Wall-clock per-fixture timeout (default 30 min): a fixture that
    runs longer is killed and recorded as `exit=timeout`.
  - Cumulative cost ceiling (default \$25): if exceeded, the sweep
    stops early and the partial table is the final output.
  - Suite results are written to disk after EACH fixture, not only at
    the end — overnight runs survive partial completion.
"""

from __future__ import annotations

import argparse
import re
import signal
import sys
import time
import traceback
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

# Project root on path so `shared.*`, `client_sdk.*`, `agent_sdk.*` resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.findings import Finding
from shared.fixtures import ALL_FIXTURES, Fixture, materialize

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LINE_TOLERANCE = 10
DEFAULT_MAX_COST = 25.0
DEFAULT_FIXTURE_TIMEOUT = 1800  # 30 minutes


def _next_suite_id(results_dir: Path) -> int:
    results_dir.mkdir(parents=True, exist_ok=True)
    used = [
        int(m.group(1))
        for p in results_dir.glob("suite_*.md")
        if (m := re.match(r"suite_(\d+)\.md$", p.name))
    ]
    return (max(used) + 1) if used else 1


def _resolve_sdk(name: str) -> tuple[Callable[..., dict[str, Any]], Path]:
    """Return (run, results_dir) for the named SDK."""
    if name == "client":
        mod = import_module("client_sdk.reviewer")
    elif name == "agent":
        mod = import_module("agent_sdk.reviewer")
    else:
        raise SystemExit(f"unknown --sdk {name!r}; expected 'client' or 'agent'")
    results_dir = PROJECT_ROOT / f"{name}_sdk" / "results"
    return mod.run, results_dir


def _expected_match(
    findings: list[Finding],
    expected: list[Finding],
    line_tolerance: int,
) -> tuple[bool, bool]:
    """Two-tier match check.

    Returns (file_hit, line_hit). `expected` is a UNION — any model
    finding matched against any expected entry counts as a hit.

    Both tiers require the **category** to match — without that, a
    finding that hits the right file/line for the *wrong reason*
    inflates the suite score (e.g. agent reports a KeyError where
    the planted bug is a CSRF). CodeRabbit caught this on PR #20.

      file_hit — same (file, category) as some expected entry. Coarse
                 "agent landed in the right neighborhood looking for
                 the right thing."
      line_hit — same (file, category) AND |line - expected.line|
                 <= line_tolerance. Stricter signal.
    """
    if not expected:
        return (not findings, not findings)

    expected_pairs = {(f.file, f.category) for f in expected}
    file_hit = any((f.file, f.category) in expected_pairs for f in findings)
    line_hit = any(
        f.file == e.file
        and f.category == e.category
        and abs(f.line - e.line) <= line_tolerance
        for f in findings
        for e in expected
    )
    return file_hit, line_hit


# --------------------------------------------------------------------------- #
# Per-fixture timeout
# --------------------------------------------------------------------------- #


class _FixtureTimeout(Exception):
    pass


def _alarm_handler(signum, frame):  # noqa: ANN001 — signal handler
    raise _FixtureTimeout("fixture exceeded wall-clock budget")


def _run_with_timeout(
    runner: Callable[..., dict[str, Any]],
    repo_path: Path,
    base_ref: str,
    head_ref: str,
    timeout_s: int,
) -> dict[str, Any]:
    """Call runner(...) under a SIGALRM-based wall clock.

    SIGALRM is process-wide on POSIX; we install our handler, set the
    alarm, and uninstall after the call. Not nestable, but the sweep
    runs fixtures sequentially so that's fine. Windows would need a
    different mechanism — out of scope for this build.
    """
    prev_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(timeout_s)
    try:
        return runner(repo_path, base_ref, head_ref)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev_handler)


# --------------------------------------------------------------------------- #
# Per-fixture run + bookkeeping
# --------------------------------------------------------------------------- #


def _run_one(
    fx: Fixture,
    runner: Callable[..., dict[str, Any]],
    line_tolerance: int,
    fixture_timeout: int,
) -> dict[str, Any]:
    print(f"\n=== {fx.name} ===", flush=True)
    started = time.time()
    error: str | None = None

    try:
        with materialize(fx) as materialized:
            result = _run_with_timeout(
                runner,
                materialized.repo,
                materialized.base_ref,
                materialized.head_ref,
                fixture_timeout,
            )
        elapsed = time.time() - started
        file_hit, line_hit = _expected_match(
            result["findings"], fx.expected, line_tolerance
        )
        row = {
            "fixture": fx.name,
            "run_id": result.get("run_id"),
            "num_turns": result.get("num_turns", 0),
            "cost_usd": result.get("cost_usd", 0.0) or 0.0,
            "num_findings": len(result.get("findings", [])),
            "expected_count": len(fx.expected),
            "file_hit": file_hit,
            "line_hit": line_hit,
            "exit_reason": result.get("exit_reason", "unknown"),
            "latency_s": elapsed,
        }
    except _FixtureTimeout:
        elapsed = time.time() - started
        error = f"timeout after {fixture_timeout}s"
        row = {
            "fixture": fx.name,
            "run_id": None,
            "num_turns": 0,
            "cost_usd": 0.0,
            "num_findings": 0,
            "expected_count": len(fx.expected),
            "file_hit": False,
            "line_hit": False,
            "exit_reason": "timeout",
            "latency_s": elapsed,
        }
    except Exception as e:  # noqa: BLE001 — sweep robustness
        elapsed = time.time() - started
        tb = traceback.format_exc()
        error = f"{type(e).__name__}: {e}"
        # Persist the traceback so we can debug after the fact.
        crash_log = PROJECT_ROOT / f"{runner.__module__.split('.')[0]}/traces" / f"crash_{fx.name}_{int(started)}.txt"
        try:
            crash_log.parent.mkdir(parents=True, exist_ok=True)
            crash_log.write_text(f"Fixture: {fx.name}\nError: {error}\n\n{tb}\n")
            print(f"  CRASH — saved traceback to {crash_log}", flush=True)
        except OSError:
            pass
        row = {
            "fixture": fx.name,
            "run_id": None,
            "num_turns": 0,
            "cost_usd": 0.0,
            "num_findings": 0,
            "expected_count": len(fx.expected),
            "file_hit": False,
            "line_hit": False,
            "exit_reason": "error",
            "latency_s": elapsed,
        }

    print(
        f"  turns={row['num_turns']:>3}  "
        f"cost=${row['cost_usd']:.4f}  "
        f"findings={row['num_findings']}  "
        f"expected_file={'Y' if row['file_hit'] else 'N'}  "
        f"expected_line+/-{line_tolerance}={'Y' if row['line_hit'] else 'N'}  "
        f"exit={row['exit_reason']}  "
        f"latency={row['latency_s']:.1f}s"
        + (f"  ({error})" if error else ""),
        flush=True,
    )
    return row


def _markdown_table(
    rows: list[dict[str, Any]],
    line_tolerance: int,
    sdk: str,
    suite_id: int,
    suite_started: float,
    completed: bool,
) -> str:
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
        f"{('run_' + str(r['run_id']).zfill(3)) if r['run_id'] is not None else '-'} |"
        for r in rows
    )
    total_cost = sum(r["cost_usd"] for r in rows)
    total_turns = sum(r["num_turns"] for r in rows)
    file_hits = sum(1 for r in rows if r["file_hit"])
    line_hits = sum(1 for r in rows if r["line_hit"])
    n = len(rows)
    elapsed = time.time() - suite_started
    state = "complete" if completed else "in progress / partial"
    summary = (
        f"\n\n**Summary ({state}):** {n} fixtures, total cost ${total_cost:.4f}, "
        f"total turns {total_turns}, file-hit {file_hits}/{n}, "
        f"line-hit {line_hits}/{n}. Wall time so far: {elapsed:.1f}s.\n"
    )
    return (
        f"# {sdk.title()} SDK reviewer suite run {suite_id:03d}\n\n"
        f"Line tolerance: +/- {line_tolerance}.  "
        f"SDK: {sdk}.\n\n"
    ) + header + body + summary


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> None:
    ap = argparse.ArgumentParser(description="Sweep a reviewer over fixtures.")
    ap.add_argument(
        "--sdk",
        choices=["client", "agent"],
        default="client",
        help="Which reviewer to drive (default: client).",
    )
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
    ap.add_argument(
        "--max-cost",
        type=float,
        default=DEFAULT_MAX_COST,
        help=f"Cumulative cost ceiling in USD (default: {DEFAULT_MAX_COST}).",
    )
    ap.add_argument(
        "--fixture-timeout",
        type=int,
        default=DEFAULT_FIXTURE_TIMEOUT,
        help=(
            f"Per-fixture wall-clock timeout in seconds "
            f"(default: {DEFAULT_FIXTURE_TIMEOUT})."
        ),
    )
    args = ap.parse_args()

    runner, results_dir = _resolve_sdk(args.sdk)

    if args.fixtures:
        wanted = {n.strip() for n in args.fixtures.split(",") if n.strip()}
        selected = [f for f in ALL_FIXTURES if f.name in wanted]
        missing = wanted - {f.name for f in selected}
        if missing:
            sys.exit(f"unknown fixtures: {sorted(missing)}")
    else:
        selected = list(ALL_FIXTURES)

    print(
        f"Sweeping {len(selected)} fixture(s) on {args.sdk!r} SDK: "
        f"{[f.name for f in selected]}"
    )
    print(
        f"Budget: max-cost=${args.max_cost:.2f}  "
        f"fixture-timeout={args.fixture_timeout}s  "
        f"line-tolerance=+/-{args.line_tolerance}"
    )

    suite_id = _next_suite_id(results_dir)
    suite_path = results_dir / f"suite_{suite_id:03d}.md"
    suite_started = time.time()
    rows: list[dict[str, Any]] = []
    cumulative_cost = 0.0

    for fx in selected:
        row = _run_one(fx, runner, args.line_tolerance, args.fixture_timeout)
        rows.append(row)
        cumulative_cost += row["cost_usd"]

        # Persist after each fixture so a crash mid-sweep doesn't lose
        # everything — the killer feature for unattended overnight runs.
        suite_path.write_text(
            _markdown_table(
                rows,
                args.line_tolerance,
                args.sdk,
                suite_id,
                suite_started,
                completed=False,
            )
        )

        if cumulative_cost >= args.max_cost:
            print(
                f"\n!! cost ceiling ${args.max_cost:.2f} reached "
                f"(cumulative=${cumulative_cost:.4f}); "
                f"stopping sweep early.",
                flush=True,
            )
            break

    suite_elapsed = time.time() - suite_started
    final_table = _markdown_table(
        rows,
        args.line_tolerance,
        args.sdk,
        suite_id,
        suite_started,
        completed=True,
    )
    suite_path.write_text(final_table)

    print()
    print(final_table)
    print(f"\nSuite wall time: {suite_elapsed:.1f}s")
    print(f"Saved: {suite_path}")


if __name__ == "__main__":
    main()
