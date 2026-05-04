"""Full agent run — one-command demo orchestrating Phases 1-6.

Reviewer runs once on launch; memory loop stays live to capture
@Working-Ant maintainer corrections in the background. SIGINT cleanly
shuts down. See README.md for the architecture story behind the
phase narration this script prints. Usage:
    uv run python scripts/full_agent_run.py <PR_URL>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

PR_URL_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$")
STATE_PATH = Path("shared/memory/learnings_state.json")
DAEMON_LOG = Path("/tmp/working_ant_memory.log")
WIDTH = 70


# ── styling helpers ─────────────────────────────────────────────────────────
def _banner(lines: list[str]) -> None:
    print()
    print("╔" + "═" * (WIDTH - 2) + "╗")
    for ln in lines:
        print(f"║ {ln:<{WIDTH - 4}} ║")
    print("╚" + "═" * (WIDTH - 2) + "╝")


def _stage(label: str) -> None:
    print(f"\n▸ {label}")


def _ok(label: str) -> None:
    print(f"  ✓ {label}")


def _detail(label: str) -> None:
    print(f"  · {label}")


# ── pipeline pieces ─────────────────────────────────────────────────────────
def _parse_pr_url(url: str) -> tuple[str, str, int]:
    m = PR_URL_RE.match(url.strip())
    if not m:
        raise ValueError(
            f"not a GitHub PR URL: {url!r} "
            "(expected https://github.com/<owner>/<repo>/pull/<n>)"
        )
    return m.group(1), m.group(2), int(m.group(3))


def _spawn_daemon(repo: str, interval: int):
    """Detached daemon; all output → log file so the demo terminal stays clean."""
    DAEMON_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_handle = open(DAEMON_LOG, "wb")
    p = subprocess.Popen(
        [
            sys.executable, "-m", "learnings.capture",
            "--repo", repo, "--watch", "--interval", str(interval),
        ],
        stdout=log_handle, stderr=subprocess.STDOUT,
        # Own process group so Ctrl-C in the parent doesn't double-signal
        # the daemon's poll loop in the middle of a Voyage call.
        preexec_fn=os.setpgrp,
    )
    time.sleep(2.0)  # let the daemon settle past its first poll
    return p


def _run_reviewer(pr_url: str) -> int:
    return subprocess.call(
        [sys.executable, "scripts/github/review_pr.py", pr_url]
    )


def _read_cursor(repo: str) -> int | None:
    if not STATE_PATH.exists():
        return None
    try:
        data = json.loads(STATE_PATH.read_text())
        v = data.get(repo)
        return int(v) if v is not None else None
    except Exception:
        return None


def _stop_daemon(daemon) -> None:
    try:
        os.killpg(os.getpgid(daemon.pid), signal.SIGTERM)
        daemon.wait(timeout=5)
    except Exception:
        pass


def _collection_for(repo: str) -> str:
    return f"learnings__{repo.replace('/', '_').lower()}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="scripts/full_agent_run.py")
    p.add_argument("pr_url", help="https://github.com/<owner>/<repo>/pull/<n>")
    p.add_argument("--interval", type=int, default=30,
                   help="memory-loop poll cadence in seconds (default 30)")
    p.add_argument("--no-daemon", action="store_true",
                   help="skip the capture daemon; review and exit")
    args = p.parse_args(argv)

    owner, repo_name, pr_n = _parse_pr_url(args.pr_url)
    repo = f"{owner}/{repo_name}"

    # Pull the live EFFORT constant + model name so the banner doesn't
    # lie when someone changes the reviewer's defaults.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from agent_sdk import reviewer as _r
    effort = _r.EFFORT
    model = _r.MODEL

    _banner([
        "Code Review Agent — Full Run",
        "",
        f"  Repository:   {repo}",
        f"  Pull Request: #{pr_n}",
        f"  Reviewer:     Agent SDK · model={model} · effort={effort}",
    ])

    daemon = None
    if not args.no_daemon:
        _stage("Initializing long-term memory")
        _detail("Voyage code-3 embeddings → Qdrant Cloud vector store")
        _detail(f"Collection: {_collection_for(repo)}")
        daemon = _spawn_daemon(repo, args.interval)
        _ok("Memory online — listening for maintainer corrections")
        _detail(f"(daemon trace: tail -f {DAEMON_LOG})")

    try:
        _stage("Running review pipeline")
        _detail("Phase 5 — fetching PR + cloning into an isolated workspace")
        _detail("Phase 4 — sandbox.LocalRepo wraps the workspace for tool I/O")
        _detail("Phase 1+2 — ODIS slice + Agent SDK tool loop")
        _detail("Phase 6 — relevant past learnings injected into the prompt")
        print()
        _run_reviewer(args.pr_url)

        if daemon is None:
            return 0

        _banner([
            "Review posted. Memory loop is live.",
            "",
            "  Tag any finding on the PR with:",
            "    @Working-Ant {learn|remember|note|teach} <text>",
            "  (or natural language — Haiku will classify it)",
            "",
            "  New corrections embed + persist to long-term memory.",
            "  Re-run this script to see them shape the next review.",
            "",
            "  Press Ctrl-C to end the session.",
        ])

        # Watch cursor and surface capture events with stylized output.
        # No auto-rerun — operator triggers the next review when ready.
        last_cursor = _read_cursor(repo)
        while True:
            time.sleep(5)
            current = _read_cursor(repo)
            if current is None:
                continue
            if last_cursor is not None and current <= last_cursor:
                continue
            _stage("Maintainer correction captured")
            _detail(f"Comment {current} extracted + AST-chunked")
            _detail("Embedded via Voyage code-3 → upserted to Qdrant")
            _ok("Long-term memory updated; will surface on the next review")
            last_cursor = current
    except KeyboardInterrupt:
        _stage("Shutting down")
    finally:
        if daemon is not None:
            _stop_daemon(daemon)
            _ok("Memory loop closed cleanly")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
