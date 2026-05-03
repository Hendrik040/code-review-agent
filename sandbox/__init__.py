"""Sandbox layer (Phase 4) — repo-as-protocol abstraction.

Two implementations:
  - LocalRepo  (sandbox.local.LocalRepo)   default; uses subprocess + tempfile
  - DaytonaRepo (sandbox.daytona.DaytonaRepo) when SANDBOX_BACKEND=daytona

Reviewers and tools talk to `Repo` only; they do not import either
backend directly. Use `materialize(fixture)` from shared.fixtures (or
the Phase 5 from_pr factory) to obtain a Repo.
"""

from sandbox.repo import ExecResult, Repo, get_backend

__all__ = ["ExecResult", "Repo", "get_backend"]
