"""DaytonaRepo — Repo implementation backed by a Daytona sandbox.

Provisions a sandbox on `__enter__`, runs every shell command inside
it via `sandbox.process.exec`, deletes the sandbox on `__exit__`. The
repo's filesystem lives at /workspace/repo inside the sandbox; the
host never sees those bytes except inside specific tool results that
the model asked for.

MVP implementation (Phase 4.1):
  - Default Daytona image (no custom OCI yet — that's Phase 4.2)
  - Bootstrap step at provisioning: create /workspace/repo, install
    ast-grep CLI via pip, upload shared/odis* into /opt/code-review-
    agent/, set git config + PYTHONPATH defaults.
  - One sandbox per review (per __enter__).

Auth: `DAYTONA_API_KEY` from the environment via `DaytonaConfig()`.
The user has this set in `.env` and `dotenv` loads it for us at
reviewer startup.

Notes on the SDK shape:
  - `Daytona.create(params=None)` returns a Sandbox.
  - `sandbox.process.exec(cmd, cwd=..., env=..., timeout=...)` returns
    an ExecuteResponse with `exit_code` and `result` (combined
    stdout+stderr — Daytona doesn't separate streams). We map both
    into our `ExecResult` with stderr="" so the wrapper layer above
    is agnostic.
  - `sandbox.fs.upload_file(data, dst, timeout=...)` writes bytes to
    an absolute path inside the sandbox. We resolve repo-relative
    paths against /workspace/repo and reject `..` traversal.
"""

from __future__ import annotations

import os
from typing import Optional

from sandbox.repo import ExecResult


# Daytona's default sandbox runs as the unprivileged `daytona` user
# (uid 1001) with home at /home/daytona; /workspace and /opt are
# root-owned and unwritable. Anchor everything inside the user's
# home so the bootstrap step succeeds without sudo.
REPO_ROOT = "/home/daytona/repo"
PYTHONPATH_ROOT = "/home/daytona/code-review-agent"

# Where to find our analysis code on the host so we can ship it into
# every fresh sandbox. Computed from this module's location so it
# survives reorganization.
import pathlib as _pl
_HOST_PROJECT_ROOT = _pl.Path(__file__).resolve().parent.parent
_HOST_SHARED_FILES = [
    "shared/__init__.py",
    "shared/odis.py",
    "shared/odis_cli.py",
]


class DaytonaRepo:
    """A throwaway Daytona sandbox.

    Construction is cheap (no API call); the sandbox is provisioned
    on `__enter__`. Use as a context manager:

        with DaytonaRepo() as repo:
            repo.exec("git init -q")
            ...

    If your fixture needs explicit resource sizing, pass kwargs:

        DaytonaRepo(cpu=2, memory=2, disk=5)
    """

    def __init__(
        self,
        *,
        cpu: Optional[int] = None,
        memory: Optional[int] = None,
        disk: Optional[int] = None,
        bootstrap_timeout: int = 180,
    ) -> None:
        self._cpu = cpu
        self._memory = memory
        self._disk = disk
        self._bootstrap_timeout = bootstrap_timeout
        self._client = None
        self._sandbox = None

    # --- lifecycle ------------------------------------------------------ #

    def __enter__(self) -> "DaytonaRepo":
        # Local imports keep `sandbox.daytona` cheap to import for any
        # consumer that only needs the type — and lets tests skip
        # importing it when DAYTONA_API_KEY is unset.
        from daytona import (
            CreateSandboxFromImageParams,
            Daytona,
            DaytonaConfig,
            Resources,
        )

        api_key = os.getenv("DAYTONA_API_KEY")
        if not api_key:
            raise RuntimeError(
                "DAYTONA_API_KEY is not set. Set it in your environment "
                "or .env file before using SANDBOX_BACKEND=daytona."
            )

        self._client = Daytona(DaytonaConfig(api_key=api_key))

        # Build resources only if any field was specified — passing an
        # empty Resources to the SDK can clamp defaults to 0.
        params = None
        if any(v is not None for v in (self._cpu, self._memory, self._disk)):
            resources = Resources(
                cpu=self._cpu,
                memory=self._memory,
                disk=self._disk,
            )
            # Default snapshot lookup is happiest when image is
            # explicit; if the user passes resource overrides we also
            # have to pin an image. Fall back to the SDK's default
            # python:3.11 image for now.
            params = CreateSandboxFromImageParams(
                image="python:3.11-slim",
                resources=resources,
            )

        self._sandbox = self._client.create(params=params)
        try:
            self._bootstrap()
        except Exception:
            # Bootstrap failure means the sandbox is in a bad state;
            # nuke it before re-raising so we don't leak resources.
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._sandbox is not None:
            try:
                self._sandbox.delete()
            except Exception:
                # Best-effort teardown; log and move on. Daytona's
                # auto-stop=15min safety net will catch a stuck
                # sandbox eventually.
                pass
            self._sandbox = None
        self._client = None

    # --- core protocol -------------------------------------------------- #

    def exec(
        self,
        cmd: str,
        cwd: str = ".",
        timeout: int = 15,
    ) -> ExecResult:
        """Run `cmd` inside the sandbox at /workspace/repo/{cwd}.

        cwd is repo-relative (".") just like LocalRepo. We resolve it
        against REPO_ROOT into an absolute sandbox path. Daytona
        merges stdout and stderr into `result`; we put it all in
        stdout and leave stderr="" so the wrapper layer doesn't have
        to know which backend it's talking to.
        """
        if self._sandbox is None:
            raise RuntimeError("DaytonaRepo.exec called outside context manager")
        abs_cwd = REPO_ROOT if cwd in (".", "") else f"{REPO_ROOT}/{cwd.lstrip('/')}"
        # ast-grep was installed via `pip install --user`, so its binary
        # lives at ~/.local/bin/ — not on the default sandbox PATH.
        # Daytona MERGES env vars (verified empirically) so we can
        # safely pass a single PATH override that prepends our user-bin
        # to whatever the sandbox configured by default.
        env = {
            "PYTHONPATH": PYTHONPATH_ROOT,
            "PATH": "/home/daytona/.local/bin:/usr/local/python/current/bin:/usr/local/bin:/usr/bin:/bin",
        }
        try:
            response = self._sandbox.process.exec(
                cmd,
                cwd=abs_cwd,
                env=env,
                timeout=timeout,
            )
        except Exception as e:  # noqa: BLE001 — surface as a non-zero exit
            return ExecResult(
                stdout="",
                stderr=f"Error: Daytona exec failed ({type(e).__name__}): {e}",
                exit_code=124,
            )
        return ExecResult(
            stdout=getattr(response, "result", "") or "",
            stderr="",
            exit_code=getattr(response, "exit_code", 0) or 0,
        )

    def upload_bytes(self, data: bytes, remote_path: str) -> None:
        """Write `data` to /workspace/repo/{remote_path} in the sandbox.

        Path-traversal is blocked the same way LocalRepo does it: any
        `..` segment in the path raises PermissionError. Daytona's
        upload_file expects an absolute destination.
        """
        if self._sandbox is None:
            raise RuntimeError("DaytonaRepo.upload_bytes called outside context manager")
        if remote_path.startswith("/") or any(seg == ".." for seg in remote_path.split("/")):
            raise PermissionError(
                f"upload_bytes path escapes repo root: {remote_path!r}"
            )
        abs_path = f"{REPO_ROOT}/{remote_path}"
        # Ensure parent dir exists. Daytona's upload_file won't mkdir
        # for us, so we do it here.
        parent = abs_path.rsplit("/", 1)[0]
        self._sandbox.process.exec(f"mkdir -p {parent}", timeout=15)
        self._sandbox.fs.upload_file(data, abs_path)

    # --- bootstrap ------------------------------------------------------ #

    def _bootstrap(self) -> None:
        """Prepare a freshly-provisioned sandbox to run reviews.

        We do four things, all of them idempotent:
          1. Create /workspace/repo and /opt/code-review-agent/shared.
          2. Install ast-grep CLI via pip if it's missing. (pip is
             already in the default Python image.)
          3. Upload our shared/__init__.py + odis.py + odis_cli.py
             so `python -m shared.odis_cli` resolves with
             PYTHONPATH=/opt/code-review-agent.
          4. Set a global git identity so `git commit` works without
             asking for one.
        """
        # Step 1 + 4: dirs + git config in one shell round-trip.
        prep = (
            f"mkdir -p {REPO_ROOT} {PYTHONPATH_ROOT}/shared && "
            "git config --global user.email fixture@local && "
            "git config --global user.name fixture && "
            "git config --global init.defaultBranch main"
        )
        r = self._raw_exec(prep, timeout=30)
        if r.exit_code != 0:
            raise RuntimeError(
                f"sandbox prep step failed: exit {r.exit_code} stdout={r.stdout!r}"
            )

        # Step 2: ast-grep via `pip install --user`. The binary lands
        # in ~/.local/bin/ which our exec() prepends to PATH for every
        # subsequent call. We don't bother with `which ast-grep`
        # before installing because the default snapshot doesn't
        # carry it; pip's idempotent so a re-run is cheap.
        install = self._raw_exec(
            "pip install --user --quiet ast-grep-cli",
            timeout=self._bootstrap_timeout,
        )
        if install.exit_code != 0:
            raise RuntimeError(
                f"ast-grep install failed: exit {install.exit_code} "
                f"stdout={install.stdout!r}"
            )
        # Verify the binary is now resolvable on the PATH our exec()
        # uses, so a tool call doesn't fail mysteriously later.
        check = self._raw_exec(
            "/home/daytona/.local/bin/ast-grep --version",
            timeout=15,
        )
        if check.exit_code != 0:
            raise RuntimeError(
                f"ast-grep post-install verification failed: "
                f"exit {check.exit_code} stdout={check.stdout!r}"
            )

        # Step 3: ship the analysis code.
        for rel in _HOST_SHARED_FILES:
            host_path = _HOST_PROJECT_ROOT / rel
            if not host_path.is_file():
                # __init__.py might not exist yet; if so create an empty one.
                if rel == "shared/__init__.py":
                    self._sandbox.fs.upload_file(b"", f"{PYTHONPATH_ROOT}/{rel}")
                    continue
                raise RuntimeError(
                    f"sandbox bootstrap: missing host file {host_path}"
                )
            self._sandbox.fs.upload_file(host_path.read_bytes(), f"{PYTHONPATH_ROOT}/{rel}")

    def _raw_exec(self, cmd: str, timeout: int = 15) -> ExecResult:
        """Like exec() but without forcing cwd into REPO_ROOT.

        Used by bootstrap for commands that need to operate on
        /opt/code-review-agent or system paths. Should never be
        called from outside this module.
        """
        try:
            response = self._sandbox.process.exec(cmd, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            return ExecResult(
                stdout="",
                stderr=f"Error: Daytona exec failed ({type(e).__name__}): {e}",
                exit_code=124,
            )
        return ExecResult(
            stdout=getattr(response, "result", "") or "",
            stderr="",
            exit_code=getattr(response, "exit_code", 0) or 0,
        )
