"""Golden test fixtures for the code-review reviewers.

A fixture is: a small Python project with a planted bug, plus the
`Finding` we expect a competent reviewer to surface for it. Phase 3's
evaluator scores reviewer output against these expected findings.

Each fixture lives in `tests/fixtures/<name>/` with two snapshot
directories `v1/` (bug-free) and `v2/` (planted bug). The loader
materializes both as commits in a temp git repo so ODIS can diff
`HEAD~1..HEAD`.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .findings import Finding

FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


@dataclass(frozen=True)
class Fixture:
    name: str
    repo_path: Path             # filesystem path to the temp git repo
    base_ref: str               # "HEAD~1" (the bug-free commit)
    head_ref: str               # "HEAD" (the commit with the planted bug)
    expected: list[Finding]     # findings a competent reviewer should surface


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _materialize(name: str, expected: list[Finding]) -> Path:
    """Create a temp git repo with two commits: v1 then v2."""
    src = FIXTURES_ROOT / name
    if not (src / "v1").is_dir() or not (src / "v2").is_dir():
        raise FileNotFoundError(f"fixture {name!r} missing v1/ or v2/ at {src}")

    repo = Path(tempfile.mkdtemp(prefix=f"fixture-{name}-"))
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "fixture@local")
    _git(repo, "config", "user.name", "fixture")

    # v1 commit
    for entry in (src / "v1").iterdir():
        if entry.is_file():
            shutil.copy2(entry, repo / entry.name)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "v1")

    # v2 commit (overwrites v1's files; same set of names)
    for entry in (src / "v2").iterdir():
        if entry.is_file():
            shutil.copy2(entry, repo / entry.name)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "v2 (planted bug)")

    return repo


@contextmanager
def materialize(fixture: Fixture) -> Iterator[Fixture]:
    """Yield a Fixture whose repo_path is a fresh temp checkout. Cleans
    up after itself."""
    repo = _materialize(fixture.name, fixture.expected)
    try:
        yield Fixture(
            name=fixture.name,
            repo_path=repo,
            base_ref=fixture.base_ref,
            head_ref=fixture.head_ref,
            expected=fixture.expected,
        )
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Concrete fixtures
# --------------------------------------------------------------------------- #

CONTRACT_MISMATCH = Fixture(
    name="contract_mismatch",
    repo_path=Path(),     # filled in by materialize()
    base_ref="HEAD~1",
    head_ref="HEAD",
    expected=[
        Finding(
            file="main.py",
            line=5,
            category="contract-mismatch",
            severity="high",
            summary="Caller passes 2 args to add(); signature now requires 3",
            detail=(
                "calc.add was changed from `add(a, b)` to `add(a, b, c)` in "
                "this diff, but the call in main.report() still passes only "
                "two arguments. This will raise TypeError at runtime."
            ),
            suggested_fix="    x = add(1, 2, 0)  # third arg required after signature change",
        ),
    ],
)


ALL_FIXTURES: list[Fixture] = [CONTRACT_MISMATCH]
