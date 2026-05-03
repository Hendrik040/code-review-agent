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
    """Create a temp git repo with two commits: v1 then v2.

    Both `v1/` and `v2/` snapshots may contain nested directories — the
    whole tree is copied via shutil.copytree(..., dirs_exist_ok=True).
    Real-world fixtures (e.g. extracted from a Sentry/Django PR) have
    deeply nested paths like `src/foo/bar.py`; we preserve them so the
    diff and imports look like the upstream repo.
    """
    src = FIXTURES_ROOT / name
    if not (src / "v1").is_dir() or not (src / "v2").is_dir():
        raise FileNotFoundError(f"fixture {name!r} missing v1/ or v2/ at {src}")

    repo = Path(tempfile.mkdtemp(prefix=f"fixture-{name}-"))
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "fixture@local")
    _git(repo, "config", "user.name", "fixture")

    # v1 commit — recursively copy the whole snapshot tree.
    shutil.copytree(src / "v1", repo, dirs_exist_ok=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "v1")

    # v2 commit — overwrites/extends v1's tree. shutil.copytree with
    # dirs_exist_ok=True merges; files at the same paths get replaced.
    # Files present in v1 but not in v2 are NOT removed (rare in real
    # PRs; we'd document or extend the fixture if a deletion test
    # requires it).
    shutil.copytree(src / "v2", repo, dirs_exist_ok=True)
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
        # The expected finding anchors at calc.py — the changed file —
        # per shared/prompts.py "Report bugs only in <file type='changed'>".
        # The caller in main.py is the *evidence* (it still passes 2 args)
        # but the bug-of-record is the breaking change in calc.py.
        Finding(
            file="calc.py",
            line=1,
            category="contract-mismatch",
            severity="high",
            summary="add() signature changed from 2 to 3 args; caller in main.py:5 still passes 2",
            detail=(
                "calc.add was changed from `add(a, b)` to `add(a, b, c)` "
                "without updating the caller `add(1, 2)` in main.py:5. "
                "Will raise TypeError at runtime."
            ),
            suggested_fix="def add(a, b, c=0):  # default makes the third arg optional",
        ),
    ],
)


SENTRY_80168 = Fixture(
    name="sentry_80168",
    repo_path=Path(),
    base_ref="HEAD~1",
    head_ref="HEAD",
    expected=[
        # Real-world bug from getsentry/sentry#80168.
        # The PR re-parents MetricAlertDetectorHandler from DetectorHandler
        # (one abstract method, `evaluate`, that the previous body
        # implemented) to StatefulDetectorHandler (an abc.ABC with FOUR
        # abstract methods: counter_names, get_dedupe_value,
        # get_group_key_values, build_occurrence_and_event_data) and
        # replaces the body with `pass`. Calling MetricAlertDetectorHandler()
        # at runtime will TypeError because none of those four methods
        # are implemented.
        Finding(
            file="src/sentry/incidents/grouptype.py",
            line=11,
            category="contract-mismatch",
            severity="high",
            summary=(
                "MetricAlertDetectorHandler subclasses the abstract "
                "StatefulDetectorHandler with `pass` and does not "
                "implement its required abstract methods"
            ),
            detail=(
                "StatefulDetectorHandler (defined in "
                "src/sentry/workflow_engine/processors/detector.py) is "
                "an abc.ABC with abstract methods counter_names, "
                "get_dedupe_value, get_group_key_values, and "
                "build_occurrence_and_event_data. The subclass body in "
                "this PR is just `pass` — none of those four methods are "
                "overridden. Instantiating MetricAlertDetectorHandler() "
                "will raise TypeError at runtime."
            ),
            suggested_fix="",
        ),
    ],
)


ALL_FIXTURES: list[Fixture] = [CONTRACT_MISMATCH, SENTRY_80168]
