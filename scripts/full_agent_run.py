"""Full agent run — one-command demo of the code-review-agent.

Given a single PR URL, this script:
  1. Spawns the capture daemon in the background (polls every --interval
     seconds for new @Working-Ant mentions on the watched repo).
  2. Runs the Agent SDK reviewer once and posts findings to the PR.
  3. Keeps the capture daemon alive afterwards so any learnings tagged
     during the demo session land in Qdrant. The reviewer does NOT
     auto-rerun — each Agent SDK review costs ~$1-2 and 5+ minutes,
     and duplicate posted reviews clutter the PR. Re-run this script
     (or scripts/github/review_pr.py) when you want a second pass
     that picks up newly-captured learnings.
  4. SIGINT (Ctrl-C) cleanly shuts down the daemon and exits.

Usage:
    uv run python scripts/full_agent_run.py <PR_URL>
"""
from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time

PR_URL_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$")


def _parse_pr_url(url: str) -> tuple[str, str, int]:
    m = PR_URL_RE.match(url.strip())
    if not m:
        raise ValueError(
            f"not a GitHub PR URL: {url!r} "
            "(expected https://github.com/<owner>/<repo>/pull/<n>)"
        )
    return m.group(1), m.group(2), int(m.group(3))


def _spawn_daemon(repo: str, interval: int) -> subprocess.Popen[bytes]:
    print(f"[run] starting capture daemon for {repo} (interval={interval}s)")
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
    print(f"[run] running reviewer on {pr_url}")
    return subprocess.call(
        [sys.executable, "scripts/github/review_pr.py", pr_url]
    )


def _stop_daemon(daemon: subprocess.Popen[bytes]) -> None:
    print("[run] stopping capture daemon")
    try:
        os.killpg(os.getpgid(daemon.pid), signal.SIGTERM)
        daemon.wait(timeout=5)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="scripts/full_agent_run.py",
        description=(
            "One-command demo of the code-review-agent. Spawns the "
            "capture daemon, runs the reviewer once on the supplied PR, "
            "then keeps the daemon alive so any @Working-Ant mentions "
            "you tag during the demo land in Qdrant. Re-run this script "
            "for another reviewer pass."
        ),
    )
    p.add_argument("pr_url", help="https://github.com/<owner>/<repo>/pull/<n>")
    p.add_argument(
        "--interval", type=int, default=30,
        help="daemon poll interval in seconds (default 30 for snappier demos)",
    )
    p.add_argument(
        "--no-daemon", action="store_true",
        help="skip the capture daemon entirely; review and exit",
    )
    args = p.parse_args(argv)

    owner, repo_name, _ = _parse_pr_url(args.pr_url)
    repo = f"{owner}/{repo_name}"

    daemon: subprocess.Popen[bytes] | None = None
    if not args.no_daemon:
        daemon = _spawn_daemon(repo, args.interval)

    try:
        _run_reviewer(args.pr_url)
        if daemon is None:
            return 0

        print()
        print(f"[run] initial review posted. Capture daemon continues polling")
        print(f"[run] {repo} every {args.interval}s.")
        print(f"[run] Tag any finding on the PR with:")
        print(f"[run]     @Working-Ant {{learn|remember|note|teach}} <text>")
        print(f"[run] (or natural language — Haiku will classify) to capture")
        print(f"[run] a learning. It lands in Qdrant; re-run this script to")
        print(f"[run] see it surface in the next review.")
        print(f"[run] Ctrl-C to quit.")
        # Block until SIGINT.
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n[run] Ctrl-C received; cleaning up...")
    finally:
        if daemon is not None:
            _stop_daemon(daemon)
        print("[run] done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
