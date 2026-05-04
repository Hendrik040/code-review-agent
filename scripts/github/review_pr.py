"""CLI: review a GitHub PR with the Agent SDK reviewer and post the result.

Usage:
    uv run python scripts/github/review_pr.py <pr_url> [--dry-run]

Pre-flight checks (fail fast before the costly reviewer call):
- GITHUB_REVIEW_BOT_TOKEN env var is set
- gh CLI is installed and authed
- PR URL parses
- PR exists (gh api succeeds)
- Working-Ant has write access to the repo (avoids opaque 403 after a 2-min clone)

Mid-run: the reviewer runs unchanged. If it raises, exit 1 (no review
posted). If it returns 0 findings, still post a "no findings" review.
If it hit max_turns without submitting, post with a warning header.

Post-time: HTTP failures print where to find the saved findings so
nothing is lost. (Reposting them is a future helper, out of scope.)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent_sdk import reviewer
from github import pr_fetch, repo_setup, trace_extract, post_review
from github.post_review import RunMeta


def _exit(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


BOT_USER = "Working-Ant"


def _preflight(pr_url: str) -> pr_fetch.PullRequest:
    if not os.environ.get("GITHUB_REVIEW_BOT_TOKEN"):
        _exit(2, "ERROR: GITHUB_REVIEW_BOT_TOKEN not set. "
                  "Add it to .env (Working-Ant token).")
    gh = shutil.which("gh")
    if gh is None:
        _exit(2, "ERROR: `gh` CLI not on PATH. Install it and run `gh auth login`.")
    auth = subprocess.run(
        [gh, "auth", "status"], capture_output=True, text=True, timeout=10,
    )
    if auth.returncode != 0:
        _exit(2, "ERROR: gh CLI not authenticated. Run `gh auth login`.")
    try:
        pr = pr_fetch.fetch_pr(pr_url)
    except ValueError as e:
        _exit(2, f"ERROR: {e}")
    except subprocess.CalledProcessError as e:
        _exit(1, f"ERROR: gh api failed (PR may not exist or be inaccessible): {e}")

    # Confirm the bot user has write access on this repo. Without this
    # check, posting fails opaquely with 403 after a 2-min clone + $1+
    # reviewer run. Fail fast here instead.
    perm_check = subprocess.run(
        [gh, "api",
         f"repos/{pr.owner}/{pr.repo}/collaborators/{BOT_USER}/permission"],
        capture_output=True, text=True, timeout=15,
    )
    if perm_check.returncode != 0:
        _exit(2, f"ERROR: {BOT_USER} is not a collaborator on "
                  f"{pr.owner}/{pr.repo}. Add as Collaborator with write access "
                  f"before running.")
    try:
        perm_data = json.loads(perm_check.stdout)
        perm = perm_data.get("permission", "none")
    except json.JSONDecodeError:
        _exit(1, f"ERROR: unexpected response from gh api collaborators check: "
                  f"{perm_check.stdout!r}")
    if perm not in ("write", "admin", "maintain"):
        _exit(2, f"ERROR: {BOT_USER} has '{perm}' access to {pr.owner}/{pr.repo}; "
                  f"need at least 'write' to post reviews.")

    return pr


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pr_url", help="https://github.com/<owner>/<repo>/pull/<n>")
    p.add_argument("--dry-run", action="store_true",
                   help="Run everything except the GH POST; print the would-be payload.")
    args = p.parse_args()

    pr = _preflight(args.pr_url)
    print(f"[1/4] Fetching PR {pr.owner}/{pr.repo}#{pr.number} ... "
          f"base={pr.base_sha[:7]} head={pr.head_sha[:7]}")
    hunks = pr_fetch.fetch_diff_hunks(pr.owner, pr.repo, pr.number)
    print(f"      {sum(len(v) for v in hunks.values())} hunks across "
          f"{len(hunks)} files")

    print(f"[2/4] Cloning {pr.owner}/{pr.repo} into a tempdir "
          f"(this may take a minute) ...")
    with repo_setup.setup_pr_repo(pr) as repo:
        print(f"[3/4] Running Agent SDK reviewer (effort={reviewer.EFFORT}) ...")
        # reviewer.run expects a Phase-4 Repo (LocalRepo/DaytonaRepo),
        # not a Path. setup_pr_repo wraps the cloned tempdir in a
        # LocalRepo and exposes it as repo.repo.
        try:
            result = reviewer.run(repo.repo, repo.base_ref, repo.head_ref)
        except Exception as e:
            _exit(1, f"ERROR: reviewer raised: {e!r}")

        print(f"      {result['num_turns']} turns, "
              f"${result['cost_usd']:.2f}, "
              f"{len(result['findings'])} findings, "
              f"exit_reason={result.get('exit_reason', 'unknown')}")

        trail = trace_extract.extract_trail(Path(result["trace_path"]))
        run_meta = RunMeta(
            run_id=result["run_id"],
            sdk="agent",
            effort=reviewer.EFFORT,
            timestamp_utc=_now_iso(),
            num_turns=result["num_turns"],
            cost_usd=result["cost_usd"],
        )
        # Reviewer hit MAX_TURNS without calling submit_findings -- the
        # findings list will likely be empty/partial; surface a warning
        # in the posted review so demo viewers aren't misled.
        truncated = (
            result.get("exit_reason") == "max_turns"
            and not result.get("submitted", True)
        )
        if truncated:
            print("      WARN: reviewer hit MAX_TURNS before submitting findings")

        trace_path = Path(result["trace_path"])
        if args.dry_run:
            print(f"[4/4] --dry-run: payload below, not posting to GH")
            payload = post_review.render_payload_for_inspection(
                pr, result["findings"], hunks, run_meta, trail,
                repo_path=repo.path, truncated=truncated, trace_path=trace_path,
            )
            print(json.dumps(payload, indent=2))
            return

        print(f"[4/4] Posting review (Run #{result['run_id']}) ...")
        token = os.environ["GITHUB_REVIEW_BOT_TOKEN"]
        try:
            url = post_review.submit_review(
                pr, result["findings"], hunks, run_meta, trail,
                token=token, repo_path=repo.path, truncated=truncated,
                trace_path=trace_path,
            )
        except RuntimeError as e:
            _exit(1, f"ERROR: GH POST failed: {e}\n"
                     f"Findings preserved at {result['result_path']}.")
        print(f"        {url}")


if __name__ == "__main__":
    main()
