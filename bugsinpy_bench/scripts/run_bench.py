"""Run a code-review SDK against prepared BugsInPy entries.

Reads prepared.json (the bench dataset produced by prepare_dataset.py)
and runs either the Agent SDK or the Client SDK reviewer at a chosen
effort level against each entry. Each per-bug result is written into a
sweep-scoped directory layout that's fully self-describing — drop a
file next to one from a different sweep / SDK / effort and the metadata
header on top tells you exactly what produced it.

Layout:
    bugsinpy_bench/results/
      sweep_<date>_<NNN>/
        meta.json                              ← sweep config snapshot
        suite.md                               ← per-bug summary table
        runs/
          <sdk>_<effort>_<project>_<bugid>.txt  ← full per-bug record
                                                 (header + SDK trace)

Each run file starts with a `# === BENCH RUN ===` block carrying:
  bench, sweep_id, bug, sdk, effort, model, branch, harness_git_rev,
  prepared_sha, introducing_commit, base_ref, head_ref,
  started/finished/duration, cost, then the original SDK output.

Usage:
    uv run python bugsinpy_bench/scripts/run_bench.py \\
        --prepared bugsinpy_bench/dataset/prepared.json \\
        --sdk agent \\
        --effort xhigh \\
        --sample 5

Run from repo root.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from agent_sdk.reviewer import run as agent_run  # noqa: E402
from client_sdk.reviewer import run as client_run  # noqa: E402
from shared.fixtures import materialize_upstream  # noqa: E402

RESULTS_ROOT = PROJECT_ROOT / "bugsinpy_bench" / "results"
BUGSINPY_PROJECTS = PROJECT_ROOT / "bugsinpy_bench" / "dataset" / "bugsinpy" / "projects"
LINE_TOLERANCE = 10
DEFAULT_BUG_TIMEOUT = 1800

VALID_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
VALID_SDKS = {"agent", "client"}


# -------------------------------------------------------------------- types --


@dataclass
class OracleRange:
    file: str
    line_start: int
    line_end: int


@dataclass
class Entry:
    project: str
    bug_id: int
    upstream_repo: str
    github_url: str
    fixed_commit: str
    introducing_commit: Optional[str]
    source: str
    oracle: list[OracleRange]


# ----------------------------------------------------------- prepared.json --


def _load_prepared(path: Path, sources: set[str]) -> list[Entry]:
    raw = json.loads(path.read_text())
    out: list[Entry] = []
    for r in raw:
        if r.get("source") not in sources:
            continue
        oracle = [OracleRange(**o) for o in r.get("oracle", [])]
        out.append(Entry(
            project=r["project"],
            bug_id=r["bug_id"],
            upstream_repo=r["upstream_repo"],
            github_url=r["github_url"],
            fixed_commit=r["fixed_commit"],
            introducing_commit=r.get("introducing_commit"),
            source=r["source"],
            oracle=oracle,
        ))
    return out


def _read_patch(project: str, bug_id: int) -> str:
    p = BUGSINPY_PROJECTS / project / "bugs" / str(bug_id) / "bug_patch.txt"
    return p.read_text(errors="replace") if p.is_file() else ""


# ------------------------------------------------------------ scoring --


def _bench_match(
    findings: list[Any], oracles: list[OracleRange], tolerance: int
) -> tuple[bool, bool]:
    """Strict file/line ±tolerance matcher.

    BugsInPy has no `category` per bug, so we drop the category check
    that scripts/run_suite.py uses. file_hit = any finding's file is
    among the oracle files; line_hit = any finding lands within
    tolerance of any oracle range bound. NOTE this is an upper bound
    on real recall (LLM-judge gives the semantic-correct number).
    """
    if not oracles:
        return (not findings, not findings)
    files = {o.file for o in oracles}
    file_hit = any(f.file in files for f in findings)
    line_hit = any(
        f.file == o.file
        and (o.line_start - tolerance) <= f.line <= (o.line_end + tolerance)
        for f in findings
        for o in oracles
    )
    return file_hit, line_hit


# ---------------------------------------------------------- timeout helper --


class _BenchTimeout(Exception):
    pass


def _alarm_handler(signum, frame):  # noqa: ANN001
    raise _BenchTimeout()


@contextmanager
def _entry_timeout(seconds: int) -> Iterator[None]:
    prev = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev)


# ----------------------------------------------------- naming + metadata --


def _sweep_root(sweep_id: str) -> Path:
    root = RESULTS_ROOT / sweep_id
    (root / "runs").mkdir(parents=True, exist_ok=True)
    return root


def _generate_sweep_id() -> str:
    """sweep_<UTC-date>_<NNN>, where NNN is the next free counter for today."""
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    pattern = re.compile(rf"sweep_{today}_(\d+)$")
    used = []
    if RESULTS_ROOT.is_dir():
        for d in RESULTS_ROOT.iterdir():
            m = pattern.match(d.name)
            if m:
                used.append(int(m.group(1)))
    nxt = (max(used) + 1) if used else 1
    return f"sweep_{today}_{nxt:03d}"


def _git_rev(path: Path) -> str:
    res = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, timeout=10
    )
    return res.stdout.strip() if res.returncode == 0 else "unknown"


def _git_branch(path: Path) -> str:
    res = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=path, capture_output=True, text=True, timeout=10,
    )
    return res.stdout.strip() if res.returncode == 0 else "unknown"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _model_name(sdk: str) -> str:
    if sdk == "agent":
        from agent_sdk.reviewer import MODEL  # type: ignore
        return MODEL
    if sdk == "client":
        from client_sdk.reviewer import MODEL  # type: ignore
        return MODEL
    return "unknown"


def _per_bug_filename(sdk: str, effort: str, entry: Entry) -> str:
    safe_proj = entry.project.replace("/", "_")
    return f"{sdk}_{effort}_{safe_proj}_{entry.bug_id}.txt"


def _label(entry: Entry) -> str:
    return f"{entry.project}#{entry.bug_id}"


# --------------------------------------------------------- run + persist --


def _run_one(
    entry: Entry,
    *,
    sdk: str,
    effort: str,
    bug_timeout: int,
    sweep_root: Path,
    sweep_id: str,
    sweep_meta: dict[str, Any],
) -> dict[str, Any]:
    print(f"\n=== {_label(entry)} ({entry.source} / {sdk} / {effort}) ===", flush=True)
    started = time.time()
    started_iso = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    error: Optional[str] = None

    head_commit = entry.introducing_commit if entry.source == "blame" else entry.fixed_commit
    if not head_commit:
        return _empty_row(entry, started, "missing_head_commit", sdk=sdk, effort=effort)
    reverse_patch = _read_patch(entry.project, entry.bug_id) if entry.source == "synthetic_revert" else None

    runner = agent_run if sdk == "agent" else client_run

    try:
        with _entry_timeout(bug_timeout):
            with materialize_upstream(
                entry.github_url,
                head_commit,
                reverse_patch=reverse_patch,
                name=f"bench-{entry.project}-{entry.bug_id}",
            ) as (repo, base_ref, head_ref):
                result = runner(repo, base_ref, head_ref, effort=effort)
        elapsed = time.time() - started
        finished_iso = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        file_hit, line_hit = _bench_match(
            result.get("findings", []), entry.oracle, LINE_TOLERANCE
        )
        row = {
            "label": _label(entry),
            "sdk": sdk,
            "effort": effort,
            "run_id": result.get("run_id"),
            "num_turns": result.get("num_turns", 0),
            "cost_usd": result.get("cost_usd", 0.0) or 0.0,
            "num_findings": len(result.get("findings", [])),
            "file_hit_strict": file_hit,
            "line_hit_strict": line_hit,
            "exit_reason": result.get("exit_reason", "unknown"),
            "latency_s": elapsed,
            "started": started_iso,
            "finished": finished_iso,
        }
        # Copy the SDK's per-run trace into the sweep dir with a header.
        _persist_per_bug(
            entry, row, sweep_root, sweep_id, sweep_meta,
            base_ref=base_ref, head_ref=head_ref, head_commit=head_commit,
        )
    except _BenchTimeout:
        elapsed = time.time() - started
        error = f"timeout after {bug_timeout}s"
        row = _empty_row(entry, started, "timeout", sdk=sdk, effort=effort, elapsed_s=elapsed)
    except Exception as e:  # noqa: BLE001
        elapsed = time.time() - started
        tb = traceback.format_exc()
        error = f"{type(e).__name__}: {e}"
        crash = sweep_root / "crashes" / f"{entry.project}_{entry.bug_id}_{int(started)}.txt"
        try:
            crash.parent.mkdir(parents=True, exist_ok=True)
            crash.write_text(f"Entry: {_label(entry)}\nError: {error}\n\n{tb}\n")
            print(f"  CRASH — saved {crash}", flush=True)
        except OSError:
            pass
        row = _empty_row(entry, started, "error", sdk=sdk, effort=effort, elapsed_s=elapsed)

    print(
        f"  turns={row['num_turns']:>3}  cost=${row['cost_usd']:.4f}  "
        f"findings={row['num_findings']}  "
        f"file={'Y' if row['file_hit_strict'] else 'N'}  "
        f"line+/-{LINE_TOLERANCE}={'Y' if row['line_hit_strict'] else 'N'}  "
        f"exit={row['exit_reason']}  latency={row['latency_s']:.1f}s"
        + (f"  ({error})" if error else ""),
        flush=True,
    )
    return row


def _empty_row(
    entry: Entry,
    started: float,
    exit_reason: str,
    *,
    sdk: str,
    effort: str,
    elapsed_s: Optional[float] = None,
) -> dict[str, Any]:
    return {
        "label": _label(entry),
        "sdk": sdk,
        "effort": effort,
        "run_id": None,
        "num_turns": 0,
        "cost_usd": 0.0,
        "num_findings": 0,
        "file_hit_strict": False,
        "line_hit_strict": False,
        "exit_reason": exit_reason,
        "latency_s": elapsed_s if elapsed_s is not None else (time.time() - started),
        "started": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "finished": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }


def _persist_per_bug(
    entry: Entry,
    row: dict[str, Any],
    sweep_root: Path,
    sweep_id: str,
    sweep_meta: dict[str, Any],
    *,
    base_ref: str,
    head_ref: str,
    head_commit: str,
) -> None:
    """Copy the SDK's auto-generated run_NNN.txt into the sweep dir,
    prepended with the BENCH RUN metadata header.
    """
    run_id = row.get("run_id")
    if run_id is None:
        return
    sdk = row["sdk"]
    src = PROJECT_ROOT / f"{sdk}_sdk" / "results" / f"run_{run_id:03d}.txt"
    if not src.is_file():
        return
    dest = sweep_root / "runs" / _per_bug_filename(sdk, row["effort"], entry)
    header = (
        "# === BENCH RUN ===\n"
        f"# bench: bugsinpy v1\n"
        f"# sweep_id: {sweep_id}\n"
        f"# bug: {_label(entry)}\n"
        f"# bug_source: {entry.source}\n"
        f"# sdk: {sdk}_sdk\n"
        f"# effort: {row['effort']}\n"
        f"# model: {sweep_meta['model']}\n"
        f"# branch: {sweep_meta['branch']}\n"
        f"# harness_git_rev: {sweep_meta['harness_git_rev']}\n"
        f"# prepared_path: {sweep_meta['prepared_path']}\n"
        f"# prepared_sha256_16: {sweep_meta['prepared_sha256_16']}\n"
        f"# upstream_repo: {entry.upstream_repo}\n"
        f"# introducing_commit: {entry.introducing_commit or '-'}\n"
        f"# fixed_commit: {entry.fixed_commit}\n"
        f"# base_ref: {base_ref}\n"
        f"# head_ref: {head_ref}\n"
        f"# started: {row['started']}\n"
        f"# finished: {row['finished']}\n"
        f"# duration_s: {row['latency_s']:.1f}\n"
        f"# cost_usd: {row['cost_usd']:.4f}\n"
        f"# num_turns: {row['num_turns']}\n"
        f"# num_findings: {row['num_findings']}\n"
        f"# file_hit_strict: {'Y' if row['file_hit_strict'] else 'N'}\n"
        f"# line_hit_strict: {'Y' if row['line_hit_strict'] else 'N'}\n"
        f"# exit_reason: {row['exit_reason']}\n"
        f"# === END BENCH ===\n\n"
    )
    dest.write_text(header + src.read_text())


# ---------------------------------------------------------- markdown table --


def _markdown_header(sweep_id: str, n_total: int, sdk: str, effort: str, model: str) -> str:
    return (
        f"# BugsInPy bench — {sdk}_sdk @ {effort} — {sweep_id}\n\n"
        f"Model: `{model}`.  Line tolerance: ±{LINE_TOLERANCE}.  N: {n_total} entries.\n\n"
        f"| entry | source | turns | cost (USD) | findings | "
        f"file hit | line ±{LINE_TOLERANCE} | exit | latency (s) | run_id |\n"
        f"|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|\n"
    )


def _markdown_row(entry: Entry, row: dict[str, Any]) -> str:
    run_id = row.get("run_id")
    return (
        f"| {_label(entry)} | {entry.source} | {row['num_turns']} | "
        f"${row['cost_usd']:.4f} | {row['num_findings']} | "
        f"{'Y' if row['file_hit_strict'] else 'N'} | "
        f"{'Y' if row['line_hit_strict'] else 'N'} | "
        f"{row['exit_reason']} | {row['latency_s']:.1f} | "
        f"{('run_' + str(run_id).zfill(3)) if run_id is not None else '-'} |\n"
    )


def _markdown_footer(rows: list[dict[str, Any]]) -> str:
    total_cost = sum(r["cost_usd"] for r in rows)
    total_turns = sum(r["num_turns"] for r in rows)
    file_hits = sum(1 for r in rows if r["file_hit_strict"])
    line_hits = sum(1 for r in rows if r["line_hit_strict"])
    n = len(rows)
    return (
        f"\n**Summary:** {n} entries, total cost ${total_cost:.4f}, "
        f"total turns {total_turns}, file-hit {file_hits}/{n}, "
        f"line-hit {line_hits}/{n}.\n"
    )


# --------------------------------------------------------------- CLI --


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepared", required=True, help="Path to prepared.json")
    ap.add_argument("--sdk", default="agent", choices=sorted(VALID_SDKS))
    ap.add_argument("--effort", default="xhigh", choices=sorted(VALID_EFFORTS))
    ap.add_argument("--sweep-id", default="",
                    help="Sweep ID. Defaults to sweep_<UTC-date>_<NNN>.")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--bug-timeout", type=int, default=DEFAULT_BUG_TIMEOUT)
    ap.add_argument("--max-cost", type=float, default=200.0)
    ap.add_argument("--sources", default="blame",
                    help="Comma-separated source filter (default: blame).")
    args = ap.parse_args()

    sources = {s.strip() for s in args.sources.split(",") if s.strip()}
    prepared_path = Path(args.prepared)
    entries = _load_prepared(prepared_path, sources)
    if args.sample > 0:
        entries = entries[: args.sample]

    sweep_id = args.sweep_id or _generate_sweep_id()
    sweep_root = _sweep_root(sweep_id)

    # Sweep config snapshot — the source of truth for traceability.
    sweep_meta = {
        "sweep_id": sweep_id,
        "started": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "sdk": args.sdk,
        "effort": args.effort,
        "model": _model_name(args.sdk),
        "branch": _git_branch(PROJECT_ROOT),
        "harness_git_rev": _git_rev(PROJECT_ROOT),
        "prepared_path": str(prepared_path),
        "prepared_sha256_16": _sha256(prepared_path),
        "sources": sorted(sources),
        "n_entries": len(entries),
        "line_tolerance": LINE_TOLERANCE,
        "bug_timeout": args.bug_timeout,
        "max_cost": args.max_cost,
    }
    (sweep_root / "meta.json").write_text(json.dumps(sweep_meta, indent=2))
    suite_path = sweep_root / "suite.md"

    print(f"Sweeping {len(entries)} entry/entries  "
          f"sdk={args.sdk} effort={args.effort}  → {sweep_root}", flush=True)
    suite_path.write_text(_markdown_header(
        sweep_id, len(entries), args.sdk, args.effort, sweep_meta["model"]
    ))
    rows: list[dict[str, Any]] = []

    suite_started = time.time()
    for entry in entries:
        row = _run_one(
            entry,
            sdk=args.sdk,
            effort=args.effort,
            bug_timeout=args.bug_timeout,
            sweep_root=sweep_root,
            sweep_id=sweep_id,
            sweep_meta=sweep_meta,
        )
        rows.append(row)
        with suite_path.open("a") as f:
            f.write(_markdown_row(entry, row))
        cum_cost = sum(r["cost_usd"] for r in rows)
        if cum_cost >= args.max_cost:
            print(f"\nStopping: cumulative cost ${cum_cost:.2f} ≥ "
                  f"--max-cost ${args.max_cost:.2f}", flush=True)
            break

    with suite_path.open("a") as f:
        f.write(_markdown_footer(rows))

    sweep_meta["finished"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    sweep_meta["wall_time_s"] = round(time.time() - suite_started, 1)
    sweep_meta["total_cost_usd"] = round(sum(r["cost_usd"] for r in rows), 4)
    (sweep_root / "meta.json").write_text(json.dumps(sweep_meta, indent=2))

    print(f"\nWall time: {sweep_meta['wall_time_s']}s")
    print(f"Saved: {suite_path}")
    print(f"Sweep: {sweep_root}")


if __name__ == "__main__":
    main()
