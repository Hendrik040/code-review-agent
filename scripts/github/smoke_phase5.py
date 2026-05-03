"""Smoke test for Phase 5 — run before demo rehearsals.

Usage:
    uv run python scripts/github/smoke_phase5.py [<sandbox_pr_url>]

Test A (no network): structural import check + env/auth check.
Test B (one real POST): runs review_pr.py against the sandbox PR.

Default sandbox PR is the one configured in PHASE5_SMOKE_PR_URL env var,
or you can pass one as argv[1]. The sandbox PR should be SEPARATE from
the actual demo PR — runs leave a real review behind.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _test_a_structural() -> None:
    print("=== Test A: structural ===")
    # Imports must work
    from agent_sdk import reviewer  # noqa: F401
    from github import pr_fetch, repo_setup, trace_extract, post_review  # noqa: F401
    print("  imports: ok")

    # Env var
    if not os.environ.get("GITHUB_REVIEW_BOT_TOKEN"):
        sys.exit("FAIL: GITHUB_REVIEW_BOT_TOKEN not set")
    print("  GITHUB_REVIEW_BOT_TOKEN: set")

    # gh CLI
    if shutil.which("gh") is None:
        sys.exit("FAIL: gh CLI not on PATH")
    auth = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if auth.returncode != 0:
        sys.exit("FAIL: gh CLI not authenticated")
    print("  gh CLI: ok\n")


def _test_b_real_post(sandbox_url: str) -> None:
    print(f"=== Test B: real POST to {sandbox_url} ===")
    print("  (this will run the agent and post one real review)\n")
    cmd = [
        "uv", "run", "python", "scripts/github/review_pr.py", sandbox_url,
    ]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        sys.exit(f"FAIL: review_pr.py exited {result.returncode}")
    print("\n  Visually verify the review URL above renders correctly in GitHub.")


def main() -> None:
    sandbox = (
        sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("PHASE5_SMOKE_PR_URL")
    )
    _test_a_structural()
    if not sandbox:
        print("SKIPPING Test B (no sandbox PR URL provided).")
        print("  Set PHASE5_SMOKE_PR_URL or pass it as argv[1].")
        return
    _test_b_real_post(sandbox)


if __name__ == "__main__":
    main()
