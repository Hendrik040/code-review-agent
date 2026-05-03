"""Get the PR's code on disk for the reviewer to read.

This module is the **Phase-4 Daytona seam**: same `setup_pr_repo(pr) ->
RepoState` interface; the local-tempdir backend is replaced with a Daytona
sandbox in Phase 4. Reviewer code (`agent_sdk/reviewer.py`) doesn't notice.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from github.pr_fetch import PullRequest

# Sentry-sized clones can take 1-3 minutes. Cap so a hung network gives up.
CLONE_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class RepoState:
    path: Path        # tmpdir root containing the cloned repo
    base_ref: str     # base SHA from the PR (passed to reviewer.run)
    head_ref: str     # head SHA from the PR


@contextmanager
def setup_pr_repo(pr: PullRequest) -> Iterator[RepoState]:
    """Clone the PR's repo into a tempdir, check out the PR head, yield.

    Cleanup runs on any exit path including KeyboardInterrupt.
    Public-fork clones use HTTPS without a token (Sentry fork is public).
    For private repos this would need the token in the URL — out of scope
    for v1.
    """
    tmp = Path(tempfile.mkdtemp(prefix=f"cra-{pr.repo}-pr{pr.number}-"))
    try:
        clone_url = f"https://github.com/{pr.owner}/{pr.repo}.git"
        repo_dir = tmp / pr.repo
        # `text=True, check=True` so any non-zero exit raises CalledProcessError
        # with stderr captured for the operator.
        subprocess.run(
            ["git", "clone", "--quiet", clone_url, str(repo_dir)],
            text=True, check=True, timeout=CLONE_TIMEOUT_SECONDS,
        )
        # Fetch the PR ref into a local branch and check it out.
        subprocess.run(
            ["git", "-C", str(repo_dir), "fetch", "origin",
             f"pull/{pr.number}/head:pr-{pr.number}"],
            text=True, check=True, timeout=CLONE_TIMEOUT_SECONDS,
        )
        subprocess.run(
            ["git", "-C", str(repo_dir), "checkout", "--quiet",
             f"pr-{pr.number}"],
            text=True, check=True, timeout=60,
        )
        yield RepoState(path=repo_dir, base_ref=pr.base_sha, head_ref=pr.head_sha)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
