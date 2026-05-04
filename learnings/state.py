"""Capture-pipeline cursor: per-repo highest-seen comment_id.

Persisted as JSON to ``shared/memory/learnings_state.json``. On daemon
restart we resume polling from the last cursor, so each comment is
processed at-least-once (Qdrant upsert is idempotent on UUIDv5 point id,
so reprocessing is safe).
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class State:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._cursors: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            if isinstance(data, dict):
                self._cursors = {k: int(v) for k, v in data.items()}
        except (json.JSONDecodeError, ValueError, OSError):
            # Treat any corruption as a clean slate. The next advance()
            # will overwrite the bad file.
            self._cursors = {}

    def cursor(self, repo: str) -> int | None:
        return self._cursors.get(repo)

    def advance(self, repo: str, comment_id: int) -> None:
        current = self._cursors.get(repo, -1)
        if comment_id > current:
            self._cursors[repo] = comment_id
            self._persist()

    def _persist(self) -> None:
        # Atomic rename so a mid-write crash never leaves a partial JSON
        # file on disk (spec §8.1: "restart picks up where it left off").
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._cursors, indent=2, sort_keys=True))
        os.replace(tmp, self._path)
