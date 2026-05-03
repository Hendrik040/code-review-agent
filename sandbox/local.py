"""LocalRepo — Repo implementation backed by a local tempdir + subprocess.

The default backend. Used by tests, by CI without DAYTONA_API_KEY, and
by anyone running the suite without a Daytona quota. Behavior matches
the pre-Phase-4 path: tempfile.mkdtemp on enter, subprocess.run for
exec, shutil.rmtree on exit.

The path-traversal guard from the old shared/agent_tools.py:_safe_target
moves here. Any upload_bytes target is resolved and rejected if it
escapes the repo root.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from sandbox.repo import ExecResult

# Project root — the directory that contains `shared/`. This path is
# pre-pended to PYTHONPATH inside LocalRepo.exec so the agent can run
# `python -m shared.odis_cli ...` regardless of cwd, matching how the
# sandbox image stages the same package at /opt/code-review-agent.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class LocalRepo:
    """A throwaway tempdir on the host filesystem.

    Constructor takes no required args; the working directory is created
    on `__enter__` and cleaned on `__exit__`. Pass `prefix` to control
    the tempdir name for debugging:

        with LocalRepo(prefix="fixture-contract_mismatch-") as repo:
            repo.exec("git init -q")
            ...

    The repo's filesystem path is exposed as `repo.path` so backends
    that need it (e.g. tar streaming for fixture init) can use it. Code
    that wants to stay backend-agnostic should call only `exec` and
    `upload_bytes`.
    """

    def __init__(
        self,
        prefix: str = "code-review-repo-",
        *,
        existing_path: Optional[Path] = None,
    ) -> None:
        """Construct a LocalRepo.

        With no args, `__enter__` creates a fresh tempdir and `__exit__`
        rmtree's it (default, used by tests + suite runner).

        With `existing_path=...`, the LocalRepo wraps a directory the
        caller already provisioned and is responsible for cleaning up;
        `__enter__/__exit__` become no-ops on the filesystem. Used by
        github/repo_setup.py so the Phase-5 PR clone (which already
        owns its tempdir's lifecycle via its own context manager) can
        be exposed to the reviewer as a `Repo` Protocol object.
        """
        self._prefix = prefix
        if existing_path is not None:
            existing_path = existing_path.resolve()
            if not existing_path.is_dir():
                raise ValueError(
                    f"existing_path must be an existing directory: {existing_path}"
                )
        self._path: Optional[Path] = existing_path
        self._owns_tempdir = existing_path is None

    @property
    def path(self) -> Path:
        if self._path is None:
            raise RuntimeError("LocalRepo path accessed outside context manager")
        return self._path

    def __enter__(self) -> "LocalRepo":
        if self._owns_tempdir:
            self._path = Path(tempfile.mkdtemp(prefix=self._prefix))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._owns_tempdir and self._path is not None:
            shutil.rmtree(self._path, ignore_errors=True)
            self._path = None

    # --- core protocol --------------------------------------------------- #

    def exec(
        self,
        cmd: str,
        cwd: str = ".",
        timeout: int = 15,
    ) -> ExecResult:
        """Run `cmd` via `bash -c` with cwd resolved relative to the repo.

        Identical semantics to the pre-Phase-4 `bash` tool — combined
        stdout/stderr returned via the dataclass; timeouts surface as
        a non-zero exit_code with stderr containing the timeout
        message rather than raising.
        """
        target_cwd = self._resolve_cwd(cwd)
        # Build a MINIMAL env from scratch — DO NOT inherit the host
        # process's full environment. The agent's `bash` tool is
        # model-callable; if we forwarded `os.environ`, the model
        # could trivially exfiltrate ANTHROPIC_API_KEY, DAYTONA_API_KEY,
        # GH_TOKEN, etc. via `echo $ANTHROPIC_API_KEY`. CR's catch on
        # PR #23. Forward only what the agent's invocations need:
        #   PATH       — to resolve git, sed, awk, ast-grep, python
        #   PYTHONPATH — for `python -m shared.odis_cli ...`
        #   HOME, LANG, LC_ALL — minimal locale + ~ resolution
        bin_dir = str(Path(sys.executable).parent)
        host_path = os.environ.get("PATH", "")
        env: dict[str, str] = {
            "PATH": bin_dir + os.pathsep + host_path,
            "PYTHONPATH": str(_PROJECT_ROOT),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        }
        try:
            proc = subprocess.run(
                ["bash", "-c", cmd],
                cwd=str(target_cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(
                stdout="",
                stderr=f"Error: command timed out after {timeout}s",
                exit_code=124,
            )
        return ExecResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
        )

    def upload_bytes(self, data: bytes, remote_path: str) -> None:
        """Write `data` to repo/remote_path, creating parents as needed.

        Path-traversal is blocked via the same `_safe_target` logic the
        old shared/agent_tools.py used: resolve the path and require it
        to stay inside the repo. Symlinks pointing outside count as
        escapes.
        """
        target = self._safe_target(remote_path)
        if target is None:
            raise PermissionError(
                f"upload_bytes path escapes repo root: {remote_path!r}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    # --- internal helpers ------------------------------------------------ #

    def _resolve_cwd(self, cwd: str) -> Path:
        """Resolve a repo-relative cwd against `self.path`.

        Defending against ``cwd="../../../etc"`` is the same problem
        path-traversal solves — we reuse `_safe_target` but allow
        directories.
        """
        if cwd in (".", ""):
            return self.path
        target = self._safe_target(cwd)
        if target is None or not target.is_dir():
            # Don't raise; the caller will see a non-zero exit_code.
            # Falling back to the repo root is safer than running with
            # an arbitrary host path.
            return self.path
        return target

    def _safe_target(self, path: str) -> Optional[Path]:
        """Port of the `_safe_target` guard from agent_tools.py.

        Resolve `repo / path` and confirm the result stays inside the
        repo root after symlink resolution. Returns None on escape.
        """
        try:
            target = (self.path / path).resolve()
            repo_resolved = self.path.resolve()
        except OSError:
            return None
        if not target.is_relative_to(repo_resolved):
            return None
        return target
