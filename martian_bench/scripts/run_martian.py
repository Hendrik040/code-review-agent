"""Run a code-review SDK against Martian's 10 Sentry PRs.

Same shape as bugsinpy_bench/scripts/run_bench.py but for Martian's
PR-based dataset. Differs in:
  - entries are real GitHub PRs (base + head SHAs, not blame-derived)
  - materialization uses materialize_pr (base != head^)
  - per-bug filename derives from PR url (repo + number)
  - oracle is free-text golden_comments (no strict file/line matcher)

Usage:
    uv run python martian_bench/scripts/run_martian.py \\
        --prepared martian_bench/dataset/prepared_martian.json \\
        --sdk agent --effort xhigh \\
        --sweep-id sweep_2026-05-04_martian_agent_xhigh
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
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
from shared.fixtures import materialize_pr  # noqa: E402

RESULTS_ROOT = PROJECT_ROOT / "martian_bench" / "results"
DEFAULT_BUG_TIMEOUT = 1800

VALID_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
VALID_SDKS = {"agent", "client"}


@dataclass
class Entry:
    pr_url: str
    pr_number: int
    repo_slug: str
    github_url: str
    original_url: str
    title: str
    base_sha: str
    head_sha: str
    goldens: list[dict[str, Any]]


def _load_prepared(path: Path) -> list[Entry]:
    raw = json.loads(path.read_text())
    return [Entry(
        pr_url=r["pr_url"], pr_number=r["pr_number"],
        repo_slug=r["repo_slug"], github_url=r["github_url"],
        original_url=r.get("original_url", ""),
        title=r.get("title", ""),
        base_sha=r["base_sha"], head_sha=r["head_sha"],
        goldens=r.get("goldens", []),
    ) for r in raw]


def _label(e: Entry) -> str:
    return f"{e.repo_slug.replace('/', '_')}#{e.pr_number}"


# --- timeout (mirror run_bench.py) ---


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


# --- naming + sweep dir ---


def _sweep_root(sweep_id: str) -> Path:
    root = RESULTS_ROOT / sweep_id
    (root / "runs").mkdir(parents=True, exist_ok=True)
    return root


def _generate_sweep_id(sdk: str, effort: str) -> str:
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    pattern = re.compile(rf"sweep_{today}_martian_{sdk}_{effort}_(\d+)$")
    used = []
    if RESULTS_ROOT.is_dir():
        for d in RESULTS_ROOT.iterdir():
            m = pattern.match(d.name)
            if m:
                used.append(int(m.group(1)))
    nxt = (max(used) + 1) if used else 1
    return f"sweep_{today}_martian_{sdk}_{effort}_{nxt:03d}"


def _git_rev(p: Path) -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=p, capture_output=True, text=True, timeout=10)
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def _git_branch(p: Path) -> str:
    r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=p,
                       capture_output=True, text=True, timeout=10)
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _model_name(sdk: str) -> str:
    if sdk == "agent":
        from agent_sdk.reviewer import MODEL  # type: ignore
        return MODEL
    if sdk == "client":
        from client_sdk.reviewer import MODEL  # type: ignore
        return MODEL
    return "unknown"


def _per_bug_filename(sdk: str, effort: str, e: Entry) -> str:
    return f"{sdk}_{effort}_{_label(e)}.txt"


# --- run + persist ---


def _run_one(
    e: Entry, *, sdk: str, effort: str, bug_timeout: int,
    sweep_root: Path, sweep_id: str, sweep_meta: dict[str, Any],
) -> dict[str, Any]:
    print(f"\n=== {_label(e)} ({sdk} / {effort}) ===", flush=True)
    started = time.time()
    started_iso = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    error: Optional[str] = None
    runner = agent_run if sdk == "agent" else client_run
    try:
        with _entry_timeout(bug_timeout):
            with materialize_pr(e.github_url, e.base_sha, e.head_sha,
                                name=f"martian-{e.repo_slug.replace('/', '-')}-{e.pr_number}") as (repo, base_ref, head_ref):
                result = runner(repo, base_ref, head_ref, effort=effort)
        elapsed = time.time() - started
        finished_iso = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        row = {
            "label": _label(e),
            "sdk": sdk, "effort": effort,
            "run_id": result.get("run_id"),
            "num_turns": result.get("num_turns", 0),
            "cost_usd": result.get("cost_usd", 0.0) or 0.0,
            "num_findings": len(result.get("findings", [])),
            "exit_reason": result.get("exit_reason", "unknown"),
            "latency_s": elapsed,
            "started": started_iso, "finished": finished_iso,
        }
        _persist_per_bug(e, row, sweep_root, sweep_id, sweep_meta,
                         base_ref=base_ref, head_ref=head_ref)
    except _BenchTimeout:
        elapsed = time.time() - started
        error = f"timeout after {bug_timeout}s"
        row = _empty(e, started, "timeout", sdk, effort, elapsed_s=elapsed)
    except Exception as exc:  # noqa: BLE001
        elapsed = time.time() - started
        tb = traceback.format_exc()
        error = f"{type(exc).__name__}: {exc}"
        crash = sweep_root / "crashes" / f"{_label(e)}_{int(started)}.txt"
        try:
            crash.parent.mkdir(parents=True, exist_ok=True)
            crash.write_text(f"Entry: {_label(e)}\nError: {error}\n\n{tb}\n")
            print(f"  CRASH — saved {crash}", flush=True)
        except OSError:
            pass
        row = _empty(e, started, "error", sdk, effort, elapsed_s=elapsed)
    print(
        f"  turns={row['num_turns']:>3}  cost=${row['cost_usd']:.4f}  "
        f"findings={row['num_findings']}  exit={row['exit_reason']}  "
        f"latency={row['latency_s']:.1f}s"
        + (f"  ({error})" if error else ""),
        flush=True,
    )
    return row


def _empty(e: Entry, started: float, exit_reason: str, sdk: str, effort: str,
           elapsed_s: Optional[float] = None) -> dict[str, Any]:
    return {
        "label": _label(e), "sdk": sdk, "effort": effort,
        "run_id": None, "num_turns": 0, "cost_usd": 0.0, "num_findings": 0,
        "exit_reason": exit_reason,
        "latency_s": elapsed_s if elapsed_s is not None else (time.time() - started),
        "started": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "finished": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }


def _persist_per_bug(e: Entry, row: dict[str, Any], sweep_root: Path, sweep_id: str,
                     sweep_meta: dict[str, Any], *, base_ref: str, head_ref: str) -> None:
    run_id = row.get("run_id")
    if run_id is None:
        return
    sdk = row["sdk"]
    src = PROJECT_ROOT / f"{sdk}_sdk" / "results" / f"run_{run_id:03d}.txt"
    if not src.is_file():
        return
    dest = sweep_root / "runs" / _per_bug_filename(sdk, row["effort"], e)
    header = (
        "# === MARTIAN RUN ===\n"
        f"# bench: martian v1\n"
        f"# sweep_id: {sweep_id}\n"
        f"# pr: {_label(e)}\n"
        f"# pr_url: {e.pr_url}\n"
        f"# original_upstream_url: {e.original_url}\n"
        f"# pr_title: {e.title}\n"
        f"# sdk: {sdk}_sdk\n"
        f"# effort: {row['effort']}\n"
        f"# model: {sweep_meta['model']}\n"
        f"# branch: {sweep_meta['branch']}\n"
        f"# harness_git_rev: {sweep_meta['harness_git_rev']}\n"
        f"# prepared_path: {sweep_meta['prepared_path']}\n"
        f"# prepared_sha256_16: {sweep_meta['prepared_sha256_16']}\n"
        f"# repo_slug: {e.repo_slug}\n"
        f"# base_sha: {e.base_sha}\n"
        f"# head_sha: {e.head_sha}\n"
        f"# n_goldens: {len(e.goldens)}\n"
        f"# started: {row['started']}\n"
        f"# finished: {row['finished']}\n"
        f"# duration_s: {row['latency_s']:.1f}\n"
        f"# cost_usd: {row['cost_usd']:.4f}\n"
        f"# num_turns: {row['num_turns']}\n"
        f"# num_findings: {row['num_findings']}\n"
        f"# exit_reason: {row['exit_reason']}\n"
        f"# === END MARTIAN ===\n\n"
    )
    dest.write_text(header + src.read_text())


# --- markdown ---


def _md_header(sweep_id: str, n: int, sdk: str, effort: str, model: str) -> str:
    return (
        f"# Martian Sentry — {sdk}_sdk @ {effort} — {sweep_id}\n\n"
        f"Model: `{model}`.  N: {n} PRs.\n\n"
        f"| pr | turns | cost (USD) | findings | exit | latency (s) | run_id |\n"
        f"|---|---:|---:|---:|---|---:|---:|\n"
    )


def _md_row(e: Entry, row: dict[str, Any]) -> str:
    rid = row.get("run_id")
    return (
        f"| {_label(e)} | {row['num_turns']} | "
        f"${row['cost_usd']:.4f} | {row['num_findings']} | "
        f"{row['exit_reason']} | {row['latency_s']:.1f} | "
        f"{('run_' + str(rid).zfill(3)) if rid is not None else '-'} |\n"
    )


def _md_footer(rows: list[dict[str, Any]]) -> str:
    n = len(rows)
    total = sum(r["cost_usd"] for r in rows)
    return f"\n**Summary:** {n} PRs, total cost ${total:.4f}.\n"


# --- main ---


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepared", required=True)
    ap.add_argument("--sdk", default="agent", choices=sorted(VALID_SDKS))
    ap.add_argument("--effort", default="xhigh", choices=sorted(VALID_EFFORTS))
    ap.add_argument("--sweep-id", default="")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--bug-timeout", type=int, default=DEFAULT_BUG_TIMEOUT)
    ap.add_argument("--max-cost", type=float, default=200.0)
    args = ap.parse_args()

    prepared_path = Path(args.prepared)
    entries = _load_prepared(prepared_path)
    if args.sample > 0:
        entries = entries[: args.sample]

    sweep_id = args.sweep_id or _generate_sweep_id(args.sdk, args.effort)
    sweep_root = _sweep_root(sweep_id)
    sweep_meta = {
        "sweep_id": sweep_id,
        "started": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "sdk": args.sdk, "effort": args.effort,
        "model": _model_name(args.sdk),
        "branch": _git_branch(PROJECT_ROOT),
        "harness_git_rev": _git_rev(PROJECT_ROOT),
        "prepared_path": str(prepared_path),
        "prepared_sha256_16": _sha256(prepared_path),
        "n_entries": len(entries),
        "bug_timeout": args.bug_timeout,
        "max_cost": args.max_cost,
    }
    (sweep_root / "meta.json").write_text(json.dumps(sweep_meta, indent=2))
    suite_path = sweep_root / "suite.md"
    print(f"Sweeping {len(entries)} PR(s)  sdk={args.sdk} effort={args.effort}  → {sweep_root}", flush=True)
    suite_path.write_text(_md_header(sweep_id, len(entries), args.sdk, args.effort, sweep_meta["model"]))

    rows: list[dict[str, Any]] = []
    suite_started = time.time()
    for e in entries:
        row = _run_one(e, sdk=args.sdk, effort=args.effort,
                       bug_timeout=args.bug_timeout,
                       sweep_root=sweep_root, sweep_id=sweep_id,
                       sweep_meta=sweep_meta)
        rows.append(row)
        with suite_path.open("a") as f:
            f.write(_md_row(e, row))
        cum = sum(r["cost_usd"] for r in rows)
        if cum >= args.max_cost:
            print(f"\nStopping: cumulative cost ${cum:.2f} ≥ --max-cost ${args.max_cost:.2f}", flush=True)
            break
    with suite_path.open("a") as f:
        f.write(_md_footer(rows))
    sweep_meta["finished"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    sweep_meta["wall_time_s"] = round(time.time() - suite_started, 1)
    sweep_meta["total_cost_usd"] = round(sum(r["cost_usd"] for r in rows), 4)
    (sweep_root / "meta.json").write_text(json.dumps(sweep_meta, indent=2))
    print(f"\nWall time: {sweep_meta['wall_time_s']}s")
    print(f"Saved: {suite_path}")


if __name__ == "__main__":
    main()
