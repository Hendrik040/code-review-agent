"""The Repo protocol — what every backend implements.

The methodology principle for Phase 4: anything that operates on the
repository runs where the repository lives. The host orchestrates the
agentic loop, the model API, and trace/result writing. The sandbox
executes everything that touches repo bytes — git, bash, ast-grep,
file IO, ODIS analysis. Tools in shared/agent_tools.py become thin
shell-idiom builders over `Repo.exec`.

Two implementations:

  LocalRepo   (sandbox.local)
    The local backend. Provisions a tempdir, runs subprocess.run for
    exec, writes bytes via Path.write_bytes. No network. Used by tests,
    by CI without DAYTONA_API_KEY, and as the apples-to-apples baseline
    in benchmarks.

  DaytonaRepo (sandbox.daytona)
    The remote sandbox backend. Provisions a Daytona sandbox on enter,
    routes exec through `sandbox.process.exec`, routes upload_bytes
    through `sandbox.fs.upload_file`, deletes the sandbox on exit.

The selection happens centrally via SANDBOX_BACKEND env var; reviewers
and tools never see the backend directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ExecResult:
    """The result of running one shell command in the repo.

    Mirrors what every backend can produce: stdout, stderr, exit code.
    Wrappers in shared/agent_tools.py build on this — they never touch
    raw subprocess.CompletedProcess or Daytona's exec response.
    """

    stdout: str
    stderr: str
    exit_code: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@runtime_checkable
class Repo(Protocol):
    """An isolated working directory the agent can operate on.

    Lifecycle is bracketed by the context-manager protocol — provision
    on enter, teardown on exit. Backends decide what "provision" and
    "teardown" mean (LocalRepo: mkdtemp + rmtree; DaytonaRepo: Daytona
    create/delete). Tools and ODIS only see this surface.
    """

    def __enter__(self) -> "Repo": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...

    def exec(
        self,
        cmd: str,
        cwd: str = ".",
        timeout: int = 15,
    ) -> ExecResult:
        """Run a shell command relative to the repo root.

        cwd is repo-relative. timeout is wall-clock seconds. Output is
        whatever the shell produced; the wrapper layer caps lengths
        (see _MAX_BASH_OUTPUT_CHARS in shared/agent_tools.py).
        """
        ...

    def upload_bytes(self, data: bytes, remote_path: str) -> None:
        """Place `data` at the given repo-relative path.

        Used by `from_fixture` to seed the repo and by `write_file` so
        the agent doesn't have to escape heredocs through the shell.
        Path-traversal is the backend's responsibility — both
        implementations reject any `remote_path` whose resolved
        absolute path escapes the repo root.
        """
        ...


# --------------------------------------------------------------------------- #
# Backend dispatcher — no backend-specific imports above this line.
# --------------------------------------------------------------------------- #


def get_backend() -> str:
    """Read SANDBOX_BACKEND env var. Defaults to 'local'.

    Centralizing this here means tools/reviewers/tests don't sprinkle
    os.getenv calls. To run the suite against Daytona:
        SANDBOX_BACKEND=daytona uv run python scripts/run_suite.py ...
    """
    return (os.getenv("SANDBOX_BACKEND") or "local").lower().strip()
