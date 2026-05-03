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
from sandbox.local import LocalRepo

# Sentry-sized clones can take 1-3 minutes. Cap so a hung network gives up.
CLONE_TIMEOUT_SECONDS = 600
# Cheap subprocess steps inside the clone — fail fast if git hangs.
GIT_CHECKOUT_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class RepoState:
    """What `setup_pr_repo` yields.

    `repo` is a Phase-4 `Repo` (LocalRepo wrapping the cloned tempdir);
    pass this into `reviewer.run(repo, base_ref, head_ref)`. `path` is
    kept as a convenience for callers that need the on-disk root
    (e.g. `review_summary._read_snippet` for orphan rendering).
    """
    repo: LocalRepo
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
            text=True, check=True, timeout=GIT_CHECKOUT_TIMEOUT_SECONDS,
        )
        # Verify HEAD matches the PR head SHA we recorded at metadata
        # fetch time. A force-push between fetch_pr() and the clone
        # would silently leave us on a different commit than what
        # findings/diff anchors expect — abort instead of misaligning.
        checked_out = subprocess.check_output(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            text=True, timeout=GIT_CHECKOUT_TIMEOUT_SECONDS,
        ).strip()
        if checked_out != pr.head_sha:
            raise RuntimeError(
                f"PR #{pr.number} head moved during clone: "
                f"checked out {checked_out}, expected {pr.head_sha}. "
                "Re-run to pick up the new head."
            )
        # Wrap the cloned dir in a LocalRepo so the reviewer (which
        # expects a Phase-4 Repo Protocol object) can drive it via
        # .exec()/.upload_bytes(). We own tempdir cleanup in the
        # finally block, so the LocalRepo is given existing_path and
        # does NOT manage its own lifecycle.
        local_repo = LocalRepo(existing_path=repo_dir)
        with local_repo:
            yield RepoState(
                repo=local_repo, path=repo_dir,
                base_ref=pr.base_sha, head_ref=pr.head_sha,
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
