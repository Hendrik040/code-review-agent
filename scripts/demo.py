"""Phase 6 demo launcher.

Spawns the capture daemon as a background subprocess and runs the
reviewer in the foreground against a target PR. Ctrl-C in the primary
terminal cleanly shuts down both. Use `--rerun` (no daemon spawn) in a
second terminal to re-review a PR while the original session's daemon
keeps polling.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time


def _spawn_daemon(repo: str, interval: int) -> subprocess.Popen[bytes]:
    print(f"[demo] starting capture daemon for {repo} (interval={interval}s)")
    p = subprocess.Popen(
        [sys.executable, "-m", "learnings.capture",
         "--repo", repo, "--watch", "--interval", str(interval)],
        # Daemon lives in its own process group so Ctrl-C in the parent
        # doesn't double-signal.
        preexec_fn=os.setpgrp,
    )
    time.sleep(2.0)  # let the daemon settle past its first poll
    return p


def _run_reviewer(repo: str, pr_number: int) -> int:
    """Drive the existing Phase 5 review_pr.py CLI."""
    pr_url = f"https://github.com/{repo}/pull/{pr_number}"
    print(f"[demo] running reviewer on {pr_url}")
    return subprocess.call(
        [sys.executable, "scripts/github/review_pr.py", pr_url]
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="scripts/demo.py")
    p.add_argument("--repo", required=True, help="owner/name")
    p.add_argument("--pr", type=int, required=True, help="PR number")
    p.add_argument("--interval", type=int, default=60,
                   help="capture daemon poll interval in seconds")
    p.add_argument("--rerun", action="store_true",
                   help="skip daemon spawn (use when one is already running elsewhere)")
    args = p.parse_args(argv)

    daemon: subprocess.Popen[bytes] | None = None
    if not args.rerun:
        daemon = _spawn_daemon(args.repo, args.interval)

    try:
        return _run_reviewer(args.repo, args.pr)
    finally:
        if daemon is not None:
            print("[demo] stopping capture daemon")
            try:
                os.killpg(os.getpgid(daemon.pid), signal.SIGTERM)
                daemon.wait(timeout=5)
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
