"""Full agent loop — one-command demo of the code-review-agent.

Given a single PR URL, this script:
  1. Spawns the capture daemon in the background (polls every --interval
     seconds for new @Working-Ant mentions on the watched repo).
  2. Runs the Agent SDK reviewer once and posts findings to the PR.
  3. Watches the daemon's state file. When a new learning is captured
     (cursor advances), automatically re-runs the reviewer so the
     freshly-stored learning surfaces in the next prompt's
     <past_learnings> block — without the operator having to touch
     the terminal again.
  4. SIGINT (Ctrl-C) cleanly shuts down both processes.

Usage:
    uv run python scripts/full_agent_loop.py <PR_URL>
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


def _parse_pr_url(url: str) -> tuple[str, str, int]:
    m = PR_URL_RE.match(url.strip())
    if not m:
        raise ValueError(
            f"not a GitHub PR URL: {url!r} "
            "(expected https://github.com/<owner>/<repo>/pull/<n>)"
        )
    return m.group(1), m.group(2), int(m.group(3))


def _spawn_daemon(repo: str, interval: int) -> subprocess.Popen[bytes]:
    print(f"[loop] starting capture daemon for {repo} (interval={interval}s)")
    p = subprocess.Popen(
        [
            sys.executable, "-m", "learnings.capture",
            "--repo", repo, "--watch", "--interval", str(interval),
        ],
        # Own process group so Ctrl-C in the parent doesn't double-signal
        # the daemon's poll loop in the middle of a Voyage call.
        preexec_fn=os.setpgrp,
    )
    time.sleep(2.0)  # let the daemon settle past its first poll
    return p


def _run_reviewer(pr_url: str) -> int:
    print(f"[loop] running reviewer on {pr_url}")
    return subprocess.call(
        [sys.executable, "scripts/github/review_pr.py", pr_url]
    )


def _read_cursor(repo: str) -> int | None:
    """Return the daemon's current cursor for ``repo``, or None if missing."""
    if not STATE_PATH.exists():
        return None
    try:
        data = json.loads(STATE_PATH.read_text())
        v = data.get(repo)
        return int(v) if v is not None else None
    except Exception:
        return None


def _stop_daemon(daemon: subprocess.Popen[bytes]) -> None:
    print("[loop] stopping capture daemon")
    try:
        os.killpg(os.getpgid(daemon.pid), signal.SIGTERM)
        daemon.wait(timeout=5)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="scripts/full_agent_loop.py",
        description=(
            "One-command demo of the code-review-agent. Spawns the "
            "capture daemon, runs the reviewer once, then auto-re-runs "
            "the reviewer whenever the daemon captures a new learning."
        ),
    )
    p.add_argument("pr_url", help="https://github.com/<owner>/<repo>/pull/<n>")
    p.add_argument(
        "--interval", type=int, default=30,
        help="daemon poll interval in seconds (default 30 for snappier demos)",
    )
    p.add_argument(
        "--no-rerun", action="store_true",
        help="post the initial review and stop watching for captures (one-shot mode)",
    )
    args = p.parse_args(argv)

    owner, repo_name, _ = _parse_pr_url(args.pr_url)
    repo = f"{owner}/{repo_name}"

    daemon = _spawn_daemon(repo, args.interval)
    try:
        # Initial review.
        _run_reviewer(args.pr_url)
        if args.no_rerun:
            print("[loop] --no-rerun set; exiting after initial review.")
            return 0

        # Snapshot the cursor so we only react to NEW captures (i.e.,
        # not whatever was already in state.json before this session).
        last_cursor = _read_cursor(repo)
        print()
        print(f"[loop] initial review posted. Now watching {repo} for new captures.")
        print(f"[loop] tag any finding on the PR with:")
        print(f"[loop]     @Working-Ant {{learn|remember|note|teach}} <text>")
        print(f"[loop] (or natural language — Haiku will classify)")
        print(f"[loop] daemon polls every {args.interval}s; this script will then")
        print(f"[loop] re-run the reviewer automatically. Ctrl-C to quit.")
        print()

        while True:
            time.sleep(5)
            current = _read_cursor(repo)
            if current is None:
                continue
            if last_cursor is not None and current <= last_cursor:
                continue
            print(f"[loop] cursor advanced ({last_cursor} -> {current}); re-running reviewer...")
            _run_reviewer(args.pr_url)
            # Re-snapshot so multiple learnings captured during the rerun
            # don't immediately re-trigger another rerun.
            last_cursor = _read_cursor(repo)
            print(f"[loop] re-review posted. Watching for next learning...\n")
    except KeyboardInterrupt:
        print("\n[loop] Ctrl-C received; cleaning up...")
    finally:
        _stop_daemon(daemon)
        print("[loop] done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
