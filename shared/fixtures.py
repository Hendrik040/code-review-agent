"""Golden test fixtures for the code-review reviewers.

A fixture is: a small Python project with a planted bug, plus the
`Finding` we expect a competent reviewer to surface for it. Phase 3's
evaluator scores reviewer output against these expected findings.

Each fixture lives in `tests/fixtures/<name>/` with two snapshot
directories `v1/` (bug-free) and `v2/` (planted bug). The loader
materializes both as commits in a fresh `Repo` (LocalRepo by default,
DaytonaRepo when SANDBOX_BACKEND=daytona) so the reviewer can diff
HEAD~1..HEAD.

Phase 4 changed the fixture loader: instead of returning a temp
directory `Path`, `materialize()` returns a `MaterializedFixture`
whose `repo: Repo` is the right backend per env var. The fixture
population (v1 commit, v2 commit) happens through `Repo.exec` and
`Repo.upload_bytes` so the same code path works against a local
tempdir or a Daytona sandbox.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from sandbox.local import LocalRepo
from sandbox.repo import Repo, get_backend

from .findings import Finding

FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


@dataclass(frozen=True)
class Fixture:
    """The spec of a fixture — name + refs + expected findings.

    Phase 4 dropped `repo_path: Path` from this dataclass; the temp
    directory was always a placeholder filled in by `materialize()`.
    The materialized result now lives in `MaterializedFixture` below.
    """

    name: str
    base_ref: str               # "HEAD~1" (the bug-free commit)
    head_ref: str               # "HEAD" (the commit with the planted bug)
    expected: list[Finding]     # findings a competent reviewer should surface


@dataclass(frozen=True)
class MaterializedFixture:
    """What `materialize(fixture)` yields.

    Carries the underlying Repo so reviewers can run their tools
    through it. The reviewer signature is
    `run(repo: Repo, base_ref: str, head_ref: str)`; this dataclass
    is what call sites unpack from the materialize() context manager.
    """

    name: str
    repo: Repo
    base_ref: str
    head_ref: str
    expected: list[Finding]


def _populate(repo: Repo, name: str) -> None:
    """Seed `repo` with two commits: v1 (bug-free) and v2 (planted bug).

    Files are uploaded one at a time through `Repo.upload_bytes`. For
    LocalRepo this is microseconds per file. For DaytonaRepo each
    upload is an HTTP round-trip; Phase 4.2 may optimize to a single
    tar upload per snapshot. For now the per-file path is the simplest
    code that works against both backends without backend-aware
    branching here.
    """
    src = FIXTURES_ROOT / name
    if not (src / "v1").is_dir() or not (src / "v2").is_dir():
        raise FileNotFoundError(
            f"fixture {name!r} missing v1/ or v2/ at {src}"
        )

    init = repo.exec(
        "git init -q -b main && "
        "git config user.email fixture@local && "
        "git config user.name fixture",
        timeout=30,
    )
    if not init.ok:
        raise RuntimeError(
            f"git init failed in fixture {name}: "
            f"exit {init.exit_code} stderr={init.stderr!r}"
        )

    # Commit messages must NOT leak oracle metadata — the agent can run
    # `git log` and read them. Earlier versions used "v2 (planted bug)"
    # which gave the reviewer a free hint about which commit introduced
    # the bug. CR's catch on PR #22; affects every sweep produced before
    # this fix.
    for i, (tag, label) in enumerate((("v1", "baseline"), ("v2", "head"))):
        snapshot_dir = src / tag
        # Before the v2 iteration, clear the working tree so files that
        # exist in v1 but NOT in v2 actually disappear in the v2 commit.
        # Without this, deleted files leak forward and the head commit
        # doesn't match the fixture's intended state. CR's catch on
        # PR #23; doesn't bite the current 7 fixtures (no deletions),
        # but would silently poison any future fixture that exercises
        # deletion semantics.
        if i > 0:
            clear = repo.exec(
                "git rm -r -q --ignore-unmatch . && git clean -fdq",
                timeout=30,
            )
            if not clear.ok:
                raise RuntimeError(
                    f"git working-tree reset failed in fixture {name} "
                    f"between {tag} commits: exit {clear.exit_code} "
                    f"stderr={clear.stderr!r}"
                )
        for path in snapshot_dir.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(snapshot_dir)
            repo.upload_bytes(path.read_bytes(), str(rel))
        commit = repo.exec(
            f'git add -A && git commit -q -m {label!r}',
            timeout=30,
        )
        if not commit.ok:
            raise RuntimeError(
                f"git commit ({tag}) failed in fixture {name}: "
                f"exit {commit.exit_code} stderr={commit.stderr!r}"
            )


def _make_repo(name: str) -> Repo:
    """Build a fresh Repo of whichever backend SANDBOX_BACKEND requests."""
    backend = get_backend()
    if backend == "local":
        return LocalRepo(prefix=f"fixture-{name}-")
    if backend == "daytona":
        # Local import — the daytona dep is optional at runtime; tests
        # and CI without DAYTONA_API_KEY shouldn't pay the import cost.
        from sandbox.daytona import DaytonaRepo
        return DaytonaRepo()
    raise ValueError(
        f"unknown SANDBOX_BACKEND={backend!r}; expected 'local' or 'daytona'"
    )


@contextmanager
def materialize(fixture: Fixture) -> Iterator[MaterializedFixture]:
    """Yield a MaterializedFixture whose repo is freshly populated.

    The repo's lifecycle is bracketed by this context manager — Repo
    cleanup (sandbox delete or tempdir rmtree) runs in the finally
    block.
    """
    repo = _make_repo(fixture.name)
    with repo:
        _populate(repo, fixture.name)
        yield MaterializedFixture(
            name=fixture.name,
            repo=repo,
            base_ref=fixture.base_ref,
            head_ref=fixture.head_ref,
            expected=fixture.expected,
        )


# --------------------------------------------------------------------------- #
# Concrete fixtures
# --------------------------------------------------------------------------- #

CONTRACT_MISMATCH = Fixture(
    name="contract_mismatch",
    base_ref="HEAD~1",
    head_ref="HEAD",
    expected=[
        # The bug-of-record is the breaking change in calc.py (added a
        # third required parameter), but the unchanged caller in main.py
        # is where the TypeError actually fires at runtime. The current
        # prompt's <finding_contract> says `file` should be "the path
        # where the bug manifests most directly" and explicitly allows
        # callers as valid anchors when their contract is broken by the
        # diff. So both anchors are acceptable; the matcher in
        # scripts/run_suite.py treats `expected` as a UNION — any
        # expected entry matched by any model finding counts as a hit.
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
        Finding(
            file="main.py",
            line=5,
            category="contract-mismatch",
            severity="high",
            summary="add(1, 2) breaks after calc.add() gained a required third argument",
            detail=(
                "main.py:5 calls `add(1, 2)`. After the diff, calc.add "
                "requires a third positional arg `c`, so the call raises "
                "TypeError at runtime when report() executes. Caller-side "
                "anchor for the same bug as the calc.py:1 entry above."
            ),
            suggested_fix="add(1, 2, 0)  # or update calc.add to default c=0",
        ),
    ],
)


SENTRY_80168 = Fixture(
    name="sentry_80168",
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


SENTRY_80528 = Fixture(
    name="sentry_80528",
    base_ref="HEAD~1",
    head_ref="HEAD",
    expected=[
        # Real-world bug from getsentry/sentry#80528.
        # `get_monitor_environment_context` builds a local copy of
        # `monitor.config` and mutates its `schedule_type` to the
        # display string, but then returns `monitor.config` (the
        # ORIGINAL, unmutated dict) under the "config" key. The local
        # `config` variable with the mutation is discarded. Callers
        # that consume the context never see the substituted
        # schedule_type display value.
        Finding(
            file="src/sentry/monitors/logic/incident_occurrence.py",
            line=168,
            category="logic",
            severity="high",
            summary=(
                "get_monitor_environment_context mutates a local "
                "`config` copy then returns `monitor.config` "
                "(unmodified) — the mutation is lost"
            ),
            detail=(
                "Lines 160-162 build `config = monitor.config.copy()` "
                "and overwrite `config['schedule_type']` with the "
                "display string. Line 168 then returns "
                "`monitor_environment.monitor.config` rather than the "
                "local `config`, so the schedule_type substitution is "
                "discarded and the context dict carries the raw enum "
                "integer instead of the display label. Any consumer "
                "(occurrence display, evidence rendering) that relies "
                "on the human-readable schedule_type sees the wrong "
                "value at runtime."
            ),
            suggested_fix="",
        ),
    ],
)


SENTRY_67876 = Fixture(
    name="sentry_67876",
    base_ref="HEAD~1",
    head_ref="HEAD",
    expected=[
        # Real-world bug from getsentry/sentry#67876.
        # The new GitHub OAuth authorize step uses `pipeline.signature`
        # as the `state` parameter both when redirecting the user to
        # GitHub and when validating the callback. `pipeline.signature`
        # is derived deterministically from the pipeline's stored state
        # and is stable across the pipeline's lifetime — it is NOT a
        # per-request random nonce. Using it as OAuth state defeats the
        # CSRF protection the `state` parameter is supposed to provide.
        Finding(
            file="src/sentry/integrations/github/integration.py",
            line=402,
            category="security",
            severity="high",
            summary=(
                "OAuth `state` parameter uses deterministic "
                "`pipeline.signature` instead of a per-request random "
                "nonce — defeats CSRF protection"
            ),
            detail=(
                "`state = pipeline.signature` (line 402) reuses a "
                "deterministic pipeline-scoped value as the OAuth "
                "`state` parameter sent to GitHub's authorize URL "
                "(line 408) and validated on callback (line 412). "
                "Because the signature is stable for the life of the "
                "pipeline (and may be predictable from observable "
                "pipeline state), an attacker who can guess or replay "
                "it can forge the callback and trick a victim into "
                "completing the GitHub install flow. The state "
                "parameter must be a fresh, unguessable, per-request "
                "random value bound to the user's session."
            ),
            suggested_fix="",
        ),
    ],
)


SENTRY_93824 = Fixture(
    name="sentry_93824",
    base_ref="HEAD~1",
    head_ref="HEAD",
    expected=[
        # Real-world bug from getsentry/sentry#93824.
        # The flusher creates worker processes via
        # `self.mp_context.Process(...)` where mp_context is a *spawn*
        # context, so the resulting object's class is
        # `multiprocessing.context.SpawnProcess`. SpawnProcess inherits
        # from `multiprocessing.process.BaseProcess`, NOT from
        # `multiprocessing.Process` (which is a context-bound alias on
        # the default context). Therefore
        # `isinstance(process, multiprocessing.Process)` is always False
        # in the spawn-context paths, so the guarded `process.kill()`
        # / `process.terminate()` calls never run.
        Finding(
            file="src/sentry/spans/consumers/process/flusher.py",
            line=254,
            category="logic",
            severity="high",
            summary=(
                "`isinstance(process, multiprocessing.Process)` is "
                "always False for SpawnProcess instances — the kill "
                "and terminate paths are dead code"
            ),
            detail=(
                "self.mp_context = multiprocessing.get_context('spawn'), "
                "and self.mp_context.Process produces a "
                "`multiprocessing.context.SpawnProcess` instance whose "
                "MRO is (SpawnProcess, BaseProcess, object). "
                "`multiprocessing.Process` is the default-context "
                "alias and is not in that MRO, so the isinstance check "
                "at line 254 (and its twin at line 346) evaluates to "
                "False even though `process` is a real worker process. "
                "Result: crashed processes are never `.kill()`'d before "
                "respawn, and on join() they are never `.terminate()`'d, "
                "potentially leaking processes or leaving the consumer "
                "hung. Correct check is "
                "`isinstance(process, multiprocessing.process.BaseProcess)`."
            ),
            suggested_fix="",
        ),
    ],
)


SENTRY_77754 = Fixture(
    name="sentry_77754",
    base_ref="HEAD~1",
    head_ref="HEAD",
    expected=[
        # Real-world bug from getsentry/sentry#77754.
        # `AssignmentSource` is a frozen dataclass with
        # `queued: datetime = timezone.now()`. The default value is
        # evaluated ONCE at class-definition time (module import), not
        # per-instance. Every AssignmentSource constructed without an
        # explicit `queued` argument shares the same timestamp — the
        # one captured at import. This breaks the contract that
        # `queued` records when the source was created.
        Finding(
            file="src/sentry/integrations/services/assignment_source.py",
            line=18,
            category="logic",
            severity="medium",
            summary=(
                "Mutable `queued: datetime = timezone.now()` default "
                "is evaluated once at class definition, not per "
                "instance"
            ),
            detail=(
                "Dataclass default values are evaluated a single time "
                "when the class body executes, so every "
                "AssignmentSource constructed without an explicit "
                "`queued=` argument receives the same timestamp — the "
                "moment this module was imported. The intended "
                "behavior is to record when the source was created. "
                "Use `field(default_factory=timezone.now)` so the "
                "callable is invoked per-instance."
            ),
            suggested_fix="",
        ),
    ],
)


SENTRY_95633 = Fixture(
    name="sentry_95633",
    base_ref="HEAD~1",
    head_ref="HEAD",
    expected=[
        # Real-world bug from getsentry/sentry#95633.
        # `queue.Queue.shutdown` was added in Python 3.13. On any
        # earlier interpreter the call raises AttributeError. The
        # surrounding `except Exception` swallows the error, but the
        # side-effect that wakes workers blocked on `q.get()` never
        # happens, so the subsequent `worker.join(timeout=5.0)` will
        # time out and graceful shutdown is broken on <3.13.
        Finding(
            file="src/sentry/remote_subscriptions/consumers/queue_consumer.py",
            line=238,
            category="contract-mismatch",
            severity="high",
            summary=(
                "`queue.Queue.shutdown()` is Python 3.13+ only — "
                "AttributeError on older runtimes silently breaks "
                "graceful shutdown"
            ),
            detail=(
                "`q.shutdown(immediate=False)` at line 238 calls a "
                "method only present on `queue.Queue` in Python "
                "3.13+. On 3.12 or earlier it raises AttributeError. "
                "The surrounding `except Exception` swallows it, but "
                "the side-effect — waking workers blocked on "
                "`q.get()` so they observe `worker.shutdown = True` — "
                "never happens, so the subsequent `worker.join("
                "timeout=5.0)` will time out and shutdown is no "
                "longer graceful. If the deployment is not pinned to "
                "3.13+, this regresses the shutdown contract."
            ),
            suggested_fix="",
        ),
    ],
)


ALL_FIXTURES: list[Fixture] = [
    CONTRACT_MISMATCH,
    SENTRY_80168,
    SENTRY_80528,
    SENTRY_67876,
    SENTRY_93824,
    SENTRY_77754,
    SENTRY_95633,
]
