# Phase 6 — Learnings (VectorDB) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement CodeRabbit-style "Learnings" — capture maintainer corrections via `@Working-Ant <call-word> <text>` mentions in PR review comments, embed at AST-unit granularity, store in Qdrant Cloud, and inject high-similarity past learnings into the reviewer's prompt on every subsequent review (plus a `search_learnings` tool for ad-hoc retrieval).

**Architecture:** Two pipelines sharing one vector store. **Capture** (`learnings/`) is a single-process daemon that polls GitHub via Phase 5's `github/pr_fetch.py` for new mentions, AST-chunks the anchored code via ast-grep, embeds with Voyage `voyage-code-3`, and upserts to Qdrant Cloud (one collection per repo). **Retrieve** (`shared/learnings.py`, ≤200 LOC, used by both reviewers) chunks the new diff with the same chunker, queries the repo's collection per AST unit, threshold-filters at cosine ≥ 0.78, runs an optional Haiku 4.5 applicability filter, and emits a `<past_learnings>` XML block into the user prompt. Both reviewers also register a `search_learnings(query)` tool. The layer is **strictly additive** — any failure must NOT block the reviewer.

**Tech Stack:** Python 3.11+, `qdrant-client` (Qdrant Cloud), `voyageai` (Voyage `voyage-code-3`), `python-dotenv`, `httpx` (already present), `ast-grep` CLI (already used at `shared/agent_tools.py:59`), `anthropic` (Haiku 4.5 for applicability filter), `pytest` + `pytest-asyncio`.

**Reference spec:** `docs/superpowers/specs/2026-05-03-phase-6-learnings-vectordb-design.md`. Read it before starting any task.

---

## File layout (lock these decisions in)

```
learnings/                              NEW package
├── __init__.py                         empty
├── config.py                           env loader, tunable defaults (§10 of spec)
├── voyage_client.py                    embed wrapper, exponential backoff
├── qdrant_store.py                     bootstrap collection, upsert, search,
│                                       collection_for(repo) naming
├── extractor.py                        regex parser, Mention dataclass
├── ast_chunker.py                      chunk_for_anchor (capture-side)
│                                     + chunks_for_diff (query-side)
├── github_adapter.py                   thin facade over github/pr_fetch.py
├── state.py                            JSON cursor: shared/memory/learnings_state.json
└── capture.py                          CLI: --once / --watch modes

shared/
├── learnings.py                        ≤ 200 LOC retrieval-side
└── skills/
    └── learnings_search.md             progressive-disclosure skill

shared/memory/
└── learnings_state.json                gitignored runtime state

github/
└── pr_fetch.py                         EDIT: +Comment dataclass, +list_open_prs,
                                        +list_pr_review_comments

client_sdk/reviewer.py                  EDIT: prompt + tool registration
agent_sdk/reviewer.py                   EDIT: prompt + MCP tool registration
shared/prompts.py                       EDIT: action_space nudge

scripts/
└── demo.py                             launcher: spawns capture daemon + reviewer

tests/test_phase6/                      NEW test package
├── __init__.py                         empty
├── conftest.py                         pytest fixtures (random test collection,
│                                       env loading)
├── fixtures/
│   ├── tiny_module.py                  AST-chunker target
│   ├── nested_class.py                 AST-chunker target
│   └── sample_diffs/                   diff fixtures for query-side
├── test_extractor.py
├── test_ast_chunker.py
├── test_voyage_client.py               (mocked)
├── test_qdrant_store.py                (live, test__unit__<random>)
├── test_state.py
├── test_shared_learnings.py            (live, test__unit__<random>)
├── test_capture.py                     (mocked github_adapter)
├── test_pr_fetch_extensions.py         (mocked subprocess)
├── test_github_adapter.py              (mocked pr_fetch)
└── test_integration_live.py            (gated behind --live flag)
```

**200-LOC budget** per new file. If a file approaches the limit during implementation, split before exceeding.

---

## Task 0: Scaffold + dependencies

**Files:**
- Modify: `pyproject.toml` — add `qdrant-client`, `voyageai` deps
- Create: `learnings/__init__.py` (empty)
- Create: `learnings/config.py`
- Create: `tests/test_phase6/__init__.py` (empty)
- Create: `tests/test_phase6/conftest.py`
- Create: `tests/test_phase6/fixtures/tiny_module.py`
- Create: `tests/test_phase6/fixtures/nested_class.py`
- Modify: `.gitignore` — add `shared/memory/learnings_state.json`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Edit `pyproject.toml`. Inside the existing `dependencies = [...]` list, append BEFORE the closing bracket:

```toml
    # Phase 6 — learnings vector DB. qdrant-client talks to Qdrant Cloud
    # (see QDRANT_URL, QDRANT_API_KEY in .env). voyageai is the embedding
    # model client (voyage-code-3, 1024d).
    "qdrant-client>=1.10.0",
    "voyageai>=0.2.3",
```

- [ ] **Step 2: Sync deps**

Run: `uv sync`
Expected: both packages installed, no version conflicts.

- [ ] **Step 3: Create empty package init**

Create `learnings/__init__.py` with no content (package marker only).

- [ ] **Step 4: Create config module**

Create `learnings/config.py`:

```python
"""Phase 6 config — env vars + tunable defaults from spec §10.

All thresholds are env-overridable so the first real-data run can
recalibrate without code changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # reads .env at worktree root


@dataclass(frozen=True)
class Config:
    voyage_api_key: str
    qdrant_url: str
    qdrant_api_key: str
    anthropic_api_key: str

    handle: str
    call_words: tuple[str, ...]
    threshold: float
    top_k: int
    per_query_k: int
    filter_enabled: bool
    interval_s: int


def load() -> Config:
    """Load config from env. Raises ValueError if required keys missing."""
    required = {
        "VOYAGE_API_KEY": os.environ.get("VOYAGE_API_KEY"),
        "QDRANT_URL": os.environ.get("QDRANT_URL"),
        "QDRANT_API_KEY": os.environ.get("QDRANT_API_KEY"),
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError(
            f"missing required env vars: {', '.join(missing)} "
            "(check .env at worktree root)"
        )
    call_words = tuple(
        w.strip() for w in
        os.environ.get("LEARNINGS_CALL_WORDS", "learn,remember,note,teach").split(",")
        if w.strip()
    )
    return Config(
        voyage_api_key=required["VOYAGE_API_KEY"],
        qdrant_url=required["QDRANT_URL"],
        qdrant_api_key=required["QDRANT_API_KEY"],
        anthropic_api_key=required["ANTHROPIC_API_KEY"],
        handle=os.environ.get("LEARNINGS_HANDLE", "@Working-Ant"),
        call_words=call_words,
        threshold=float(os.environ.get("LEARNINGS_THRESHOLD", "0.78")),
        top_k=int(os.environ.get("LEARNINGS_TOP_K", "5")),
        per_query_k=int(os.environ.get("LEARNINGS_PER_QUERY_K", "5")),
        filter_enabled=os.environ.get("LEARNINGS_FILTER", "1") == "1",
        interval_s=int(os.environ.get("LEARNINGS_INTERVAL", "60")),
    )
```

- [ ] **Step 5: Create test scaffolding**

Create `tests/test_phase6/__init__.py` (empty).

Create `tests/test_phase6/conftest.py`:

```python
"""Phase 6 test fixtures.

Uses live Qdrant Cloud with random per-test collections (per spec §9 —
no in-memory mode). Tests are gated by env vars so CI can skip them
gracefully if credentials aren't configured.
"""
from __future__ import annotations

import os
import secrets
from collections.abc import Iterator

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from learnings.config import load as load_config


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run integration tests against live Voyage + Qdrant Cloud + Anthropic.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="needs --live flag")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def cfg():
    """Config loaded from .env. Skips if env not configured."""
    try:
        return load_config()
    except ValueError as e:
        pytest.skip(f"phase 6 env not configured: {e}")


@pytest.fixture
def random_collection_name() -> str:
    """Unique collection name for one test."""
    return f"test__unit__{secrets.token_hex(8)}"


@pytest.fixture
def qdrant_test_collection(cfg, random_collection_name) -> Iterator[tuple[QdrantClient, str]]:
    """Create + tear down a real Qdrant Cloud collection for one test.

    Runs against the same cluster as production but in an isolated
    test__unit__<random> namespace. Free tier handles the load.
    """
    client = QdrantClient(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key)
    client.create_collection(
        collection_name=random_collection_name,
        vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
    )
    try:
        yield client, random_collection_name
    finally:
        try:
            client.delete_collection(collection_name=random_collection_name)
        except Exception:
            pass  # Best-effort cleanup; don't mask the real test failure.
```

Create `tests/test_phase6/fixtures/tiny_module.py`:

```python
"""Test fixture for the AST chunker. DO NOT IMPORT — code is read as text."""
GLOBAL_CONST = 42


def first_function(x: int) -> int:
    """Adds one."""
    return x + 1


def second_function(y: int) -> int:
    """Adds two."""
    inner = y + 2
    return inner
```

Create `tests/test_phase6/fixtures/nested_class.py`:

```python
"""Test fixture: nested class with methods. Read as text, not imported."""


class OuterClass:
    """Top-level class with a couple of methods."""

    CLASS_CONST = "hello"

    def method_one(self, value: int) -> int:
        """First method."""
        return value * 2

    def method_two(self, items: list[int]) -> int:
        """Second method, multi-line."""
        total = 0
        for item in items:
            total += item
        return total
```

- [ ] **Step 6: Update .gitignore**

Append to `.gitignore`:

```
# Phase 6 — runtime state for capture daemon
shared/memory/learnings_state.json
```

- [ ] **Step 7: Verify config loads**

Run: `uv run python -c "from learnings.config import load; print(load())"`
Expected: prints a `Config(...)` repr without raising. (Requires the `.env` to have all 4 keys; skip if not yet configured and document.)

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock learnings/ tests/test_phase6/ .gitignore
git commit -m "phase 6: scaffold learnings/ + config + test fixtures + deps"
```

---

## Task 1: Voyage embed client

**Files:**
- Create: `learnings/voyage_client.py`
- Create: `tests/test_phase6/test_voyage_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_phase6/test_voyage_client.py`:

```python
"""Voyage client unit tests — voyageai is mocked.

We don't burn real API calls in CI; we assert request shape +
retry behavior.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from learnings.voyage_client import VoyageClient, VoyageError


def test_embed_single_returns_1024d_vector():
    fake_result = MagicMock()
    fake_result.embeddings = [[0.0] * 1024]
    with patch("learnings.voyage_client.voyageai.Client") as mock_cls:
        mock_cls.return_value.embed.return_value = fake_result
        c = VoyageClient(api_key="fake")
        vec = c.embed_one("def foo(): pass", input_type="document")
        assert len(vec) == 1024
        mock_cls.return_value.embed.assert_called_once_with(
            ["def foo(): pass"], model="voyage-code-3", input_type="document"
        )


def test_embed_query_uses_query_input_type():
    fake_result = MagicMock()
    fake_result.embeddings = [[0.0] * 1024]
    with patch("learnings.voyage_client.voyageai.Client") as mock_cls:
        mock_cls.return_value.embed.return_value = fake_result
        c = VoyageClient(api_key="fake")
        c.embed_one("query text", input_type="query")
        _, kwargs = mock_cls.return_value.embed.call_args
        assert kwargs["input_type"] == "query"


def test_embed_retries_on_transient_error_then_succeeds():
    fake_result = MagicMock()
    fake_result.embeddings = [[0.0] * 1024]
    side_effects = [Exception("503"), Exception("503"), fake_result]
    with patch("learnings.voyage_client.voyageai.Client") as mock_cls, \
         patch("learnings.voyage_client.time.sleep") as mock_sleep:
        mock_cls.return_value.embed.side_effect = side_effects
        c = VoyageClient(api_key="fake", max_retries=4)
        vec = c.embed_one("text")
        assert len(vec) == 1024
        assert mock_cls.return_value.embed.call_count == 3
        # Backoff schedule: 1s, 2s after the first two failures.
        assert mock_sleep.call_args_list == [((1,),), ((2,),)]


def test_embed_raises_after_max_retries():
    with patch("learnings.voyage_client.voyageai.Client") as mock_cls, \
         patch("learnings.voyage_client.time.sleep"):
        mock_cls.return_value.embed.side_effect = Exception("503")
        c = VoyageClient(api_key="fake", max_retries=4)
        with pytest.raises(VoyageError):
            c.embed_one("text")
        assert mock_cls.return_value.embed.call_count == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_phase6/test_voyage_client.py -v`
Expected: ImportError — `learnings.voyage_client` doesn't exist yet.

- [ ] **Step 3: Implement voyage_client.py**

Create `learnings/voyage_client.py`:

```python
"""Voyage AI embedding client wrapper for Phase 6.

Wraps `voyageai.Client` with explicit `voyage-code-3` model selection,
exponential backoff (1s, 2s, 4s, 8s) on transient failures, and a
batch entry point. Per spec §6: 1024d vectors, cosine-distance store.
"""
from __future__ import annotations

import time
from typing import Literal

import voyageai

InputType = Literal["document", "query"]


class VoyageError(RuntimeError):
    """Raised when embedding fails after exhausting retries."""


class VoyageClient:
    MODEL = "voyage-code-3"
    BACKOFF_SCHEDULE_S = (1, 2, 4, 8)

    def __init__(self, api_key: str, max_retries: int = 4) -> None:
        self._client = voyageai.Client(api_key=api_key)
        self._max_retries = max_retries

    def embed_one(self, text: str, *, input_type: InputType = "document") -> list[float]:
        """Embed a single text. Returns 1024-dim vector."""
        return self.embed_batch([text], input_type=input_type)[0]

    def embed_batch(
        self, texts: list[str], *, input_type: InputType = "document"
    ) -> list[list[float]]:
        """Embed N texts in one API call. Backoff + retry on errors."""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                result = self._client.embed(texts, model=self.MODEL, input_type=input_type)
                return list(result.embeddings)
            except Exception as e:
                last_exc = e
                if attempt + 1 < self._max_retries:
                    time.sleep(self.BACKOFF_SCHEDULE_S[attempt])
        raise VoyageError(f"voyage embed failed after {self._max_retries} attempts") from last_exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_phase6/test_voyage_client.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add learnings/voyage_client.py tests/test_phase6/test_voyage_client.py
git commit -m "phase 6: voyage client wrapper + retries"
```

---

## Task 2: Qdrant store

**Files:**
- Create: `learnings/qdrant_store.py`
- Create: `tests/test_phase6/test_qdrant_store.py`

- [ ] **Step 1: Write the failing tests (live Qdrant)**

Create `tests/test_phase6/test_qdrant_store.py`:

```python
"""Qdrant store tests — live against Qdrant Cloud test__unit__<random>.

Per spec §9: no in-memory mode; tests use real cluster, isolated by
random collection names, torn down via the qdrant_test_collection
fixture.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from qdrant_client.models import Distance, VectorParams

from learnings.qdrant_store import (
    LearningPayload,
    QdrantStore,
    collection_for,
    point_id_for,
)


def test_collection_for_slugifies_repo():
    assert collection_for("Hendrik040/code-review-agent") == "learnings__hendrik040_code-review-agent"
    assert collection_for("OWNER/REPO") == "learnings__owner_repo"


def test_point_id_for_is_deterministic_uuid5():
    a = point_id_for("owner/repo", 12345)
    b = point_id_for("owner/repo", 12345)
    c = point_id_for("owner/repo", 12346)
    assert a == b
    assert a != c
    uuid.UUID(a)  # must parse as UUID


def test_bootstrap_creates_collection_if_missing(cfg, random_collection_name):
    store = QdrantStore(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key)
    try:
        assert store.bootstrap(random_collection_name) is True  # created
        assert store.bootstrap(random_collection_name) is False  # already exists
    finally:
        store.client.delete_collection(collection_name=random_collection_name)


def _sample_payload() -> LearningPayload:
    return LearningPayload(
        code_chunk_text="def foo(): return 1",
        learning_text="always return 1",
        repo="owner/repo",
        pr_number=42,
        file_path="src/foo.py",
        line_start=1,
        line_end=1,
        chunk_kind="function",
        language="python",
        author="someone",
        captured_at=datetime.now(timezone.utc).isoformat(),
        commit_sha="abc123",
    )


def test_upsert_and_search_roundtrip(qdrant_test_collection):
    client, name = qdrant_test_collection
    store = QdrantStore.from_client(client)
    pid = point_id_for("owner/repo", 1)
    vec = [0.1] * 1024
    store.upsert(name, point_id=pid, vector=vec, payload=_sample_payload())
    hits = store.search(name, query_vector=vec, k=5)
    assert len(hits) == 1
    assert hits[0].payload["learning_text"] == "always return 1"
    assert hits[0].score > 0.99  # identical vector


def test_upsert_is_idempotent_on_same_id(qdrant_test_collection):
    client, name = qdrant_test_collection
    store = QdrantStore.from_client(client)
    pid = point_id_for("owner/repo", 1)
    p1 = _sample_payload()
    store.upsert(name, point_id=pid, vector=[0.1] * 1024, payload=p1)
    p2 = LearningPayload(**{**p1.__dict__, "learning_text": "updated"})
    store.upsert(name, point_id=pid, vector=[0.1] * 1024, payload=p2)
    hits = store.search(name, query_vector=[0.1] * 1024, k=5)
    assert len(hits) == 1
    assert hits[0].payload["learning_text"] == "updated"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_phase6/test_qdrant_store.py -v`
Expected: ImportError — `learnings.qdrant_store` doesn't exist.

- [ ] **Step 3: Implement qdrant_store.py**

Create `learnings/qdrant_store.py`:

```python
"""Qdrant Cloud store for Phase 6 learnings.

One collection per repo (named ``learnings__<repo-slug>``), 1024d cosine
vectors (Voyage voyage-code-3). Point IDs are deterministic UUIDv5 over
``f"{repo}:{comment_id}"`` so re-processing the same comment overwrites
the same point — no duplicates.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

VECTOR_SIZE = 1024  # voyage-code-3
DISTANCE = Distance.COSINE
COLLECTION_PREFIX = "learnings__"


def collection_for(repo: str) -> str:
    """Slug a 'owner/name' into a Qdrant-safe collection identifier."""
    slug = repo.lower().replace("/", "_")
    return f"{COLLECTION_PREFIX}{slug}"


def point_id_for(repo: str, comment_id: int | str) -> str:
    """Deterministic UUIDv5 for (repo, comment_id). See spec §6."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{repo}:{comment_id}"))


@dataclass(frozen=True)
class LearningPayload:
    code_chunk_text: str
    learning_text: str
    repo: str
    pr_number: int
    file_path: str
    line_start: int
    line_end: int
    chunk_kind: str       # "function" | "method" | "module-scope" | "fallback_window"
    language: str
    author: str
    captured_at: str      # ISO-8601 UTC
    commit_sha: str


@dataclass(frozen=True)
class Hit:
    score: float
    payload: dict[str, Any]
    point_id: str


class QdrantStore:
    def __init__(self, url: str, api_key: str) -> None:
        self.client = QdrantClient(url=url, api_key=api_key)

    @classmethod
    def from_client(cls, client: QdrantClient) -> "QdrantStore":
        obj = cls.__new__(cls)
        obj.client = client
        return obj

    def bootstrap(self, collection: str) -> bool:
        """Create the collection if missing. Returns True if created."""
        if self.client.collection_exists(collection_name=collection):
            return False
        self.client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=DISTANCE),
        )
        return True

    def upsert(
        self,
        collection: str,
        *,
        point_id: str,
        vector: list[float],
        payload: LearningPayload,
    ) -> None:
        self.bootstrap(collection)
        self.client.upsert(
            collection_name=collection,
            points=[PointStruct(id=point_id, vector=vector, payload=asdict(payload))],
        )

    def search(
        self,
        collection: str,
        *,
        query_vector: list[float],
        k: int = 5,
    ) -> list[Hit]:
        if not self.client.collection_exists(collection_name=collection):
            return []
        result = self.client.query_points(
            collection_name=collection, query=query_vector, limit=k, with_payload=True
        )
        return [
            Hit(score=p.score, payload=p.payload or {}, point_id=str(p.id))
            for p in result.points
        ]
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_phase6/test_qdrant_store.py -v`
Expected: 5 passed (slow — talking to Qdrant Cloud).

If tests skip (env not configured): set `.env` with `QDRANT_URL` and `QDRANT_API_KEY`, then re-run.

- [ ] **Step 5: Commit**

```bash
git add learnings/qdrant_store.py tests/test_phase6/test_qdrant_store.py
git commit -m "phase 6: qdrant store — collection per repo, UUIDv5 ids, idempotent upsert"
```

---

## Task 3: State / cursor file

**Files:**
- Create: `learnings/state.py`
- Create: `tests/test_phase6/test_state.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_phase6/test_state.py`:

```python
"""Cursor file: tracks the highest-seen comment_id per repo."""
from __future__ import annotations

from pathlib import Path

from learnings.state import State


def test_advance_and_load_roundtrip(tmp_path: Path):
    p = tmp_path / "state.json"
    s = State(p)
    assert s.cursor("owner/repo") is None
    s.advance("owner/repo", 100)
    assert s.cursor("owner/repo") == 100

    # New instance reads from disk.
    s2 = State(p)
    assert s2.cursor("owner/repo") == 100


def test_advance_only_moves_forward(tmp_path: Path):
    s = State(tmp_path / "state.json")
    s.advance("owner/repo", 100)
    s.advance("owner/repo", 50)
    assert s.cursor("owner/repo") == 100  # never regress


def test_per_repo_isolation(tmp_path: Path):
    s = State(tmp_path / "state.json")
    s.advance("a/b", 1)
    s.advance("c/d", 99)
    assert s.cursor("a/b") == 1
    assert s.cursor("c/d") == 99


def test_corrupt_file_is_treated_as_empty(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text("not json {{{")
    s = State(p)
    assert s.cursor("owner/repo") is None
    s.advance("owner/repo", 5)
    assert s.cursor("owner/repo") == 5
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_phase6/test_state.py -v`
Expected: ImportError on `learnings.state`.

- [ ] **Step 3: Implement state.py**

Create `learnings/state.py`:

```python
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
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_phase6/test_state.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add learnings/state.py tests/test_phase6/test_state.py
git commit -m "phase 6: per-repo cursor state for capture daemon"
```

---

## Task 4: Mention extractor

**Files:**
- Create: `learnings/extractor.py`
- Create: `tests/test_phase6/test_extractor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_phase6/test_extractor.py`:

```python
"""Mention extractor — regex built from configured handle + call words."""
from __future__ import annotations

import pytest

from learnings.extractor import Extractor, Mention

DEFAULT_WORDS = ("learn", "remember", "note", "teach")


@pytest.fixture
def ex() -> Extractor:
    return Extractor(handle="@Working-Ant", call_words=DEFAULT_WORDS)


def test_basic_mention(ex: Extractor):
    m = ex.parse("@Working-Ant learn always use .$apply")
    assert m == Mention(call_word="learn", text="always use .$apply")


def test_handle_case_insensitive(ex: Extractor):
    m = ex.parse("@working-ant remember: handle nulls")
    assert m == Mention(call_word="remember", text="handle nulls")


def test_call_word_case_insensitive(ex: Extractor):
    m = ex.parse("@Working-Ant LEARN: x")
    assert m == Mention(call_word="LEARN", text="x")


def test_optional_punctuation(ex: Extractor):
    assert ex.parse("@Working-Ant note - foo") == Mention(call_word="note", text="foo")
    assert ex.parse("@Working-Ant note: foo") == Mention(call_word="note", text="foo")
    assert ex.parse("@Working-Ant note. foo") == Mention(call_word="note", text="foo")
    assert ex.parse("@Working-Ant note foo") == Mention(call_word="note", text="foo")


def test_multi_line_body_collapsed(ex: Extractor):
    assert ex.parse("@Working-Ant teach\nfoo bar baz") == Mention(call_word="teach", text="foo bar baz")


def test_wrong_handle_returns_none(ex: Extractor):
    assert ex.parse("@OtherBot learn x") is None


def test_wrong_call_word_returns_none(ex: Extractor):
    assert ex.parse("@Working-Ant fix x") is None


def test_empty_text_returns_none(ex: Extractor):
    assert ex.parse("@Working-Ant learn   ") is None


def test_normal_comment_returns_none(ex: Extractor):
    assert ex.parse("Looks good to me") is None


def test_extractor_escapes_handle_with_regex_chars():
    """LEARNINGS_HANDLE could contain regex metachars; must be escaped."""
    ex = Extractor(handle="@bot.x+y", call_words=DEFAULT_WORDS)
    assert ex.parse("@bot.x+y learn ok") == Mention(call_word="learn", text="ok")
    # The literal regex shouldn't loosely match a different handle.
    assert ex.parse("@botxxxy learn no") is None


def test_only_first_mention_captured(ex: Extractor):
    """Pin the contract: bodies with multiple mentions yield only the first.
    See Spec §4 — one learning per comment body."""
    body = (
        "@Working-Ant learn first lesson\n\n"
        "@Working-Ant note second lesson"
    )
    m = ex.parse(body)
    assert m is not None
    assert m.call_word == "learn"
    assert m.text == "first lesson"
    # The second mention is dropped, not concatenated.
    assert "@Working-Ant" not in m.text
    assert "second" not in m.text


def test_trailing_prose_after_blank_line_is_dropped(ex: Extractor):
    """Maintainers often write a learning then continue normal review prose;
    the prose must not end up embedded in the learning text."""
    body = (
        "@Working-Ant teach use .$apply not Reflect.apply\n\n"
        "LGTM otherwise — please also rename foo to bar."
    )
    m = ex.parse(body)
    assert m is not None
    assert m.call_word == "teach"
    assert m.text == "use .$apply not Reflect.apply"
    assert "LGTM" not in m.text
    assert "rename" not in m.text


def test_single_line_body_still_works(ex: Extractor):
    """The blank-line terminator must not break the single-line common case."""
    m = ex.parse("@Working-Ant learn always X")
    assert m == Mention(call_word="learn", text="always X")


def test_multi_line_within_one_paragraph_collapsed(ex: Extractor):
    """Newlines INSIDE the same paragraph (no blank line between) collapse
    into spaces — already covered by test_multi_line_body_collapsed but
    pin it here in the new termination semantics too."""
    m = ex.parse("@Working-Ant teach line one\nline two\nline three")
    assert m == Mention(call_word="teach", text="line one line two line three")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_phase6/test_extractor.py -v`
Expected: ImportError on `learnings.extractor`.

- [ ] **Step 3: Implement extractor.py**

Create `learnings/extractor.py`:

```python
"""@mention parser for capture pipeline.

Builds the regex dynamically from the configured handle + call-word list
(both ``re.escape``'d) so users can rebrand without code changes. Spec §4.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Mention:
    call_word: str       # the matched call word, as written by the maintainer
    text: str            # the captured learning text, whitespace-normalized


class Extractor:
    def __init__(self, handle: str, call_words: tuple[str, ...]) -> None:
        if not call_words:
            raise ValueError("at least one call word required")
        words_alt = "|".join(re.escape(w) for w in call_words)
        pattern = (
            re.escape(handle)
            + r"\s+(" + words_alt + r")\b\s*[:.\-]?\s*(.+?)(?:\n\s*\n|\Z)"
        )
        # DOTALL lets the body span multiple lines; the (?:\n\s*\n|\Z)
        # terminator stops the capture at the first blank line so trailing
        # PR-comment prose doesn't end up embedded in the learning text.
        self._re = re.compile(pattern, re.IGNORECASE | re.DOTALL)

    def parse(self, body: str) -> Mention | None:
        """Return the FIRST mention in body, or None.

        Bodies with multiple `@handle <call-word> ...` mentions are not
        supported — only the first is captured. This matches Spec §4's
        "one learning per comment" contract.
        """
        m = self._re.search(body)
        if not m:
            return None
        text = " ".join(m.group(2).split())  # collapse whitespace, drop newlines
        if not text:
            return None
        return Mention(call_word=m.group(1), text=text)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_phase6/test_extractor.py -v`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add learnings/extractor.py tests/test_phase6/test_extractor.py
git commit -m "phase 6: extractor — @mention parser with configurable handle/call-words"
```

---

## Task 5: AST chunker (capture-side)

**Files:**
- Create: `learnings/ast_chunker.py`
- Create: `tests/test_phase6/test_ast_chunker.py`

- [ ] **Step 1: Write the failing test (capture-side first)**

Create `tests/test_phase6/test_ast_chunker.py`:

```python
"""AST chunker — function/method/module-scope extraction via ast-grep.

Capture-side: chunk_for_anchor(file, line_range) -> Chunk
Query-side:   chunks_for_diff(repo_path, changed) -> list[Chunk]
              (added in Task 7)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from learnings.ast_chunker import Chunk, chunk_for_anchor

FIXTURES = Path(__file__).parent / "fixtures"


def test_chunk_for_anchor_returns_enclosing_function():
    # tiny_module.py: first_function spans 5..7, second spans 10..13
    c = chunk_for_anchor(FIXTURES / "tiny_module.py", line_start=6, line_end=6)
    assert c.kind == "function"
    assert c.line_start == 5 and c.line_end == 7
    assert "def first_function" in c.text
    assert "second_function" not in c.text


def test_chunk_for_anchor_returns_enclosing_method():
    # nested_class.py: method_one is inside OuterClass
    c = chunk_for_anchor(FIXTURES / "nested_class.py", line_start=10, line_end=10)
    assert c.kind == "method"
    assert "def method_one" in c.text
    assert "def method_two" not in c.text


def test_chunk_for_anchor_falls_back_for_module_scope():
    # Anchor on the GLOBAL_CONST line (line 3) — ast-grep succeeds but
    # no function encloses → kind="module-scope" (NOT "fallback_window";
    # fallback_window is reserved for ast-grep failures).
    c = chunk_for_anchor(FIXTURES / "tiny_module.py", line_start=3, line_end=3)
    assert c.kind == "module-scope"
    assert "GLOBAL_CONST" in c.text


def test_chunk_for_anchor_picks_smallest_enclosing_unit():
    # nested_class.py: line inside method_two (lines 13..18) should
    # return the METHOD, not the enclosing class.
    c = chunk_for_anchor(FIXTURES / "nested_class.py", line_start=18, line_end=18)
    assert c.kind == "method"
    assert "def method_two" in c.text
    assert "def method_one" not in c.text


def test_chunk_for_anchor_expands_to_cover_full_range():
    # Multi-line range that crosses two functions — no single function
    # encloses the range, so ast-grep "succeeds with no enclosing match"
    # path fires → kind="module-scope".
    c = chunk_for_anchor(FIXTURES / "tiny_module.py", line_start=6, line_end=11)
    assert c.kind == "module-scope"


def test_chunk_for_anchor_uses_fallback_window_on_ast_failure(tmp_path):
    """ast-grep returncode ≠ (0,1) raises RuntimeError, which the
    chunker converts to kind='fallback_window' — distinct from
    'module-scope' which means ast-grep succeeded with no enclosing match."""
    from unittest.mock import patch
    src = tmp_path / "x.py"
    src.write_text("def foo():\n    return 1\n")
    with patch("learnings.ast_chunker._collect_nodes", side_effect=RuntimeError("simulated")):
        c = chunk_for_anchor(src, line_start=1, line_end=1)
    assert c.kind == "fallback_window"
    assert "def foo" in c.text
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_phase6/test_ast_chunker.py -v`
Expected: ImportError on `learnings.ast_chunker`.

- [ ] **Step 3: Implement ast_chunker.py (capture-side only)**

Create `learnings/ast_chunker.py`:

```python
"""AST-based chunker for Phase 6.

Uses ``ast-grep`` (already required by the project; see
``shared/agent_tools.py:59``) to find function and class-method boundaries.
The same chunker runs at capture-time (single anchor → enclosing unit) and
query-time (diff → all changed enclosing units; see Task 7).

Python-only for v1. Multi-language requires per-language patterns.
"""
from __future__ import annotations

import json
import logging
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

# ast-grep patterns. $$$ matches any sequence; $NAME matches an identifier.
# `def $NAME($$$)` catches both sync and async functions — tree-sitter
# Python represents them both as `function_definition` nodes, so the
# pattern matches both forms. Each captured node's range covers the
# entire definition (header + body) — there is no ":" or trailing
# `: $$$` in the pattern because that confuses ast-grep's matcher in
# 0.42.x and produces zero matches.
_PY_FUNC_PATTERN = "def $NAME($$$)"
_PY_CLASS_PATTERN = "class $NAME"

_AST_TIMEOUT_S = 15.0
_FALLBACK_WINDOW = 50  # lines on each side when no AST unit fits


@dataclass(frozen=True)
class Chunk:
    text: str
    kind: str                 # "function" | "method" | "module-scope" | "fallback_window"
    line_start: int           # 1-indexed, inclusive
    line_end: int             # 1-indexed, inclusive


@dataclass(frozen=True)
class _AstNode:
    text: str
    line_start: int
    line_end: int
    kind: str                 # "function" or "class"
    parent_class_line_start: int | None  # for "method" detection


def _run_ast_grep(file: Path, pattern: str) -> list[dict]:
    cmd = (
        f"ast-grep run -p {shlex.quote(pattern)} "
        f"--lang python --json=stream {shlex.quote(str(file))}"
    )
    proc = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=_AST_TIMEOUT_S
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"ast-grep failed: {proc.stderr}")
    out: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _collect_nodes(file: Path) -> list[_AstNode]:
    """Find every function, async function, and class. Mark methods
    (functions whose enclosing parent is a class) at output time."""
    src = file.read_text()
    src_lines = src.splitlines()
    classes = _run_ast_grep(file, _PY_CLASS_PATTERN)
    funcs = _run_ast_grep(file, _PY_FUNC_PATTERN)

    def _span(node: dict) -> tuple[int, int, str]:
        # ast-grep uses 0-indexed line numbers in `range.start.line`.
        s = node["range"]["start"]["line"] + 1
        e = node["range"]["end"]["line"] + 1
        text = "\n".join(src_lines[s - 1 : e])
        return s, e, text

    class_spans = [(*_span(c), "class") for c in classes]
    func_spans = [(*_span(f), "function") for f in funcs]

    def _find_parent_class(s: int) -> int | None:
        for cs, ce, _, _ in class_spans:
            if cs < s <= ce:
                return cs
        return None

    out: list[_AstNode] = []
    for s, e, text, _ in func_spans:
        out.append(
            _AstNode(
                text=text,
                line_start=s,
                line_end=e,
                kind="function",
                parent_class_line_start=_find_parent_class(s),
            )
        )
    for s, e, text, _ in class_spans:
        out.append(
            _AstNode(text=text, line_start=s, line_end=e, kind="class", parent_class_line_start=None)
        )
    return out


def chunk_for_anchor(file: Path, *, line_start: int, line_end: int) -> Chunk:
    """Find the smallest AST unit (function/method) fully containing
    [line_start, line_end].

    Returns:
      - kind="function" or "method" if a function/method encloses the range
      - kind="module-scope" if ast-grep succeeded but no function encloses
        the anchor (the anchor IS at module level — top-level statements,
        constants, etc.)
      - kind="fallback_window" if ast-grep itself failed (timeout, parse
        error, etc.) — we don't actually know where the anchor sits.
    """
    if line_end < line_start:
        line_start, line_end = line_end, line_start

    try:
        nodes = _collect_nodes(file)
    except Exception as exc:
        # Spec §8.1 — log + fall back, never block the pipeline.
        logging.warning("ast chunker fell back: file=%s err=%s", file, exc)
        return _fallback_window(file, line_start, line_end, kind="fallback_window")

    enclosing = [
        n for n in nodes
        if n.line_start <= line_start and line_end <= n.line_end and n.kind == "function"
    ]
    if not enclosing:
        # ast-grep ran fine; the anchor really is at module scope.
        return _fallback_window(file, line_start, line_end, kind="module-scope")

    # Smallest function that fully contains the range.
    n = min(enclosing, key=lambda x: x.line_end - x.line_start)
    kind = "method" if n.parent_class_line_start is not None else "function"
    return Chunk(text=n.text, kind=kind, line_start=n.line_start, line_end=n.line_end)


def _fallback_window(
    file: Path, line_start: int, line_end: int, *, kind: str = "fallback_window"
) -> Chunk:
    """Build a ±50-line window around the anchor. Caller chooses `kind`
    to communicate WHY the fallback fired (see chunk_for_anchor docstring)."""
    src_lines = file.read_text().splitlines()
    n = len(src_lines)
    s = max(1, line_start - _FALLBACK_WINDOW)
    e = min(n, line_end + _FALLBACK_WINDOW)
    text = "\n".join(src_lines[s - 1 : e])
    return Chunk(text=text, kind=kind, line_start=s, line_end=e)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_phase6/test_ast_chunker.py -v`
Expected: 6 passed. If `ast-grep` not installed, install via `brew install ast-grep` or `cargo install ast-grep`.

- [ ] **Step 5: Commit**

```bash
git add learnings/ast_chunker.py tests/test_phase6/test_ast_chunker.py
git commit -m "phase 6: ast chunker — capture-side chunk_for_anchor + fallback window"
```

---

## Task 6: AST chunker (query-side)

**Files:**
- Modify: `learnings/ast_chunker.py` — add `chunks_for_diff`
- Modify: `tests/test_phase6/test_ast_chunker.py` — add query-side tests
- Create: `tests/test_phase6/fixtures/sample_diffs/single_func_change.diff`

- [ ] **Step 1: Create a sample diff fixture**

Create `tests/test_phase6/fixtures/sample_diffs/single_func_change.diff`:

```
diff --git a/tiny_module.py b/tiny_module.py
index abc..def 100644
--- a/tiny_module.py
+++ b/tiny_module.py
@@ -5,3 +5,3 @@
 def first_function(x: int) -> int:
     """Adds one."""
-    return x + 1
+    return x + 100
```

- [ ] **Step 2: Add the failing test**

Append to `tests/test_phase6/test_ast_chunker.py`:

```python
from learnings.ast_chunker import chunks_for_diff


def test_chunks_for_diff_returns_changed_function():
    # Hand-roll the changed-line map directly: one file, one changed line.
    repo_path = FIXTURES  # treat fixtures dir as repo root
    changed = {"tiny_module.py": [7]}
    chunks = chunks_for_diff(repo_path, changed)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.kind == "function"
    assert "first_function" in c.text


def test_chunks_for_diff_dedupes_within_one_function():
    # Multiple changed lines inside the same function -> one chunk.
    changed = {"tiny_module.py": [6, 7]}
    chunks = chunks_for_diff(FIXTURES, changed)
    assert len(chunks) == 1


def test_chunks_for_diff_skips_missing_files():
    chunks = chunks_for_diff(FIXTURES, {"does_not_exist.py": [1]})
    assert chunks == []


def test_chunks_for_diff_handles_module_scope_changes():
    # Line 3 (GLOBAL_CONST) — no enclosing function. Should still
    # produce a chunk via the fallback path.
    chunks = chunks_for_diff(FIXTURES, {"tiny_module.py": [3]})
    assert len(chunks) == 1
    assert chunks[0].kind in ("module-scope", "fallback_window")
```

- [ ] **Step 3: Run tests, verify they fail on the new ones**

Run: `uv run pytest tests/test_phase6/test_ast_chunker.py -v`
Expected: ImportError on `chunks_for_diff` (function not yet defined).

- [ ] **Step 4: Add chunks_for_diff to ast_chunker.py**

Append to `learnings/ast_chunker.py`:

```python
def chunks_for_diff(repo_path: Path, changed: dict[str, list[int]]) -> list[Chunk]:
    """Given a map of {file_path: [changed_line_numbers]}, return the
    deduplicated set of enclosing AST units that contain any changed line.

    `changed` is provided by the caller — typically derived from the
    Phase-5 diff hunks (post-image RIGHT side) or from ``git diff``.
    """
    out: list[Chunk] = []
    seen: set[tuple[str, int, int]] = set()  # (file, line_start, line_end)
    for file_path, lines in changed.items():
        full_path = repo_path / file_path
        if not full_path.exists():
            continue
        try:
            nodes = _collect_nodes(full_path)
        except Exception:
            continue
        funcs = [n for n in nodes if n.kind == "function"]
        for line in lines:
            enclosing = [
                n for n in funcs
                if n.line_start <= line <= n.line_end
            ]
            if enclosing:
                n = min(enclosing, key=lambda x: x.line_end - x.line_start)
                key = (file_path, n.line_start, n.line_end)
                if key in seen:
                    continue
                seen.add(key)
                kind = "method" if n.parent_class_line_start is not None else "function"
                out.append(Chunk(text=n.text, kind=kind, line_start=n.line_start, line_end=n.line_end))
            else:
                # No enclosing function — fall back to a small window.
                c = _fallback_window(full_path, line, line)
                key = (file_path, c.line_start, c.line_end)
                if key in seen:
                    continue
                seen.add(key)
                out.append(c)
    return out
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `uv run pytest tests/test_phase6/test_ast_chunker.py -v`
Expected: 9 passed (5 from Task 5 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add learnings/ast_chunker.py tests/test_phase6/test_ast_chunker.py tests/test_phase6/fixtures/sample_diffs/
git commit -m "phase 6: ast chunker — query-side chunks_for_diff with dedupe"
```

---

## Task 7: Shared learnings module (retrieve + format + tool handler)

**Files:**
- Create: `shared/learnings.py`
- Create: `tests/test_phase6/test_shared_learnings.py`

This is the load-bearing retrieval module used by both reviewers. Hard cap: 200 LOC.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_phase6/test_shared_learnings.py`:

```python
"""Shared retrieval module — read path used by both SDK reviewers.

retrieve_for_diff -> applicability_filter -> format_for_prompt is the
end-to-end flow; search_tool_handler is the search_learnings tool body.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from learnings.qdrant_store import (
    LearningPayload,
    QdrantStore,
    collection_for,
    point_id_for,
)
from shared.learnings import (
    Hit,
    apply_threshold,
    format_for_prompt,
    retrieve_for_diff,
    search_tool_handler,
)


def _payload(text: str = "always use X") -> LearningPayload:
    return LearningPayload(
        code_chunk_text="def foo(): pass",
        learning_text=text,
        repo="owner/repo",
        pr_number=1,
        file_path="src/foo.py",
        line_start=1,
        line_end=2,
        chunk_kind="function",
        language="python",
        author="someone",
        captured_at=datetime.now(timezone.utc).isoformat(),
        commit_sha="sha",
    )


def test_apply_threshold_drops_below_floor():
    hits = [
        Hit(score=0.9, payload={}, point_id="a"),
        Hit(score=0.7, payload={}, point_id="b"),
    ]
    kept = apply_threshold(hits, threshold=0.78)
    assert [h.point_id for h in kept] == ["a"]


def test_format_for_prompt_emits_xml_block():
    h = Hit(
        score=0.84,
        payload=_payload("use X").__dict__ | {"language": "python"},
        point_id="abc",
    )
    out = format_for_prompt([h])
    assert "<past_learnings>" in out
    assert "<intro>" in out
    assert "<learning>use X</learning>" in out
    assert 'score="0.84"' in out
    assert 'file="src/foo.py"' in out


def test_format_for_prompt_empty_hits_returns_empty_string():
    assert format_for_prompt([]) == ""


def test_retrieve_for_diff_seeded_then_queried(qdrant_test_collection, cfg):
    """End-to-end with hand-built vectors (Voyage mocked)."""
    client, name = qdrant_test_collection
    store = QdrantStore.from_client(client)
    seed_vec = [0.1] * 1024
    store.upsert(
        name,
        point_id=point_id_for("owner/repo", 1),
        vector=seed_vec,
        payload=_payload("seeded learning"),
    )

    fake_voyage = MagicMock()
    fake_voyage.embed_one.return_value = seed_vec  # query == seed -> max score

    # No diff machinery — call retrieve_for_diff with pre-computed chunks.
    from learnings.ast_chunker import Chunk
    chunks = [Chunk(text="def foo(): pass", kind="function", line_start=1, line_end=2)]
    hits = retrieve_for_diff(
        repo="owner/repo",
        chunks=chunks,
        store=store,
        embedder=fake_voyage,
        collection_override=name,
        per_query_k=5,
        threshold=0.78,
    )
    assert len(hits) == 1
    assert hits[0].payload["learning_text"] == "seeded learning"


def test_retrieve_for_diff_dedupes_across_chunks(qdrant_test_collection, cfg):
    client, name = qdrant_test_collection
    store = QdrantStore.from_client(client)
    seed_vec = [0.1] * 1024
    store.upsert(
        name, point_id=point_id_for("owner/repo", 1),
        vector=seed_vec, payload=_payload("L"),
    )
    fake = MagicMock()
    fake.embed_one.return_value = seed_vec
    from learnings.ast_chunker import Chunk
    chunks = [
        Chunk(text="a", kind="function", line_start=1, line_end=2),
        Chunk(text="b", kind="function", line_start=3, line_end=4),
    ]
    hits = retrieve_for_diff(
        repo="owner/repo", chunks=chunks, store=store,
        embedder=fake, collection_override=name,
        per_query_k=5, threshold=0.78,
    )
    assert len(hits) == 1  # same point_id even though queried twice


def test_search_tool_handler_returns_xml_items(qdrant_test_collection, cfg):
    client, name = qdrant_test_collection
    store = QdrantStore.from_client(client)
    seed_vec = [0.1] * 1024
    store.upsert(
        name, point_id=point_id_for("owner/repo", 1),
        vector=seed_vec, payload=_payload("L"),
    )
    fake = MagicMock()
    fake.embed_one.return_value = seed_vec
    out = search_tool_handler(
        query="how do I do X",
        repo="owner/repo",
        store=store,
        embedder=fake,
        collection_override=name,
        k=3,
    )
    assert "<item" in out
    assert "<learning>L</learning>" in out


def test_retrieve_for_diff_returns_empty_on_store_failure():
    """Spec §8 — fail-open: store errors yield empty hits."""
    broken = MagicMock()
    broken.search.side_effect = Exception("network down")
    fake_embed = MagicMock()
    fake_embed.embed_one.return_value = [0.1] * 1024
    from learnings.ast_chunker import Chunk
    chunks = [Chunk(text="x", kind="function", line_start=1, line_end=2)]
    hits = retrieve_for_diff(
        repo="owner/repo", chunks=chunks, store=broken,
        embedder=fake_embed, collection_override="anything",
        per_query_k=5, threshold=0.78,
    )
    assert hits == []


def test_render_item_escapes_cdata_terminator_in_code():
    """A code_chunk_text containing the literal `]]>` (rare in Python,
    common in JS/TS/SVG) must not close the CDATA section early.
    Without the escape, the parser would see </original_code> early
    and the rest of the chunk would inject as raw XML."""
    h = Hit(
        score=0.9,
        payload=_payload("L").__dict__ | {
            "code_chunk_text": "const html = `<svg>data]]> garbage`",
        },
        point_id="x",
    )
    out = format_for_prompt([h])
    # The literal `]]>` from the input must be split across two CDATA
    # sections so the FIRST `]]>` in the output belongs to our escape,
    # not to the malicious payload.
    assert "data]]]]><![CDATA[> garbage" in out
    # And the closing original_code tag is still in the right place
    # (i.e. not consumed by the early CDATA terminator).
    assert "</original_code>" in out


def test_applicability_filter_bails_to_threshold_on_haiku_exception():
    """Spec §8.2: Haiku failure → skip filter, pass through threshold-only.
    The whole step bails (NOT per-hit) so output is never a mix of judged
    and un-judged hits."""
    from shared.learnings import applicability_filter

    hits = [
        Hit(score=0.9, payload={"learning_text": "a"}, point_id="1"),
        Hit(score=0.85, payload={"learning_text": "b"}, point_id="2"),
        Hit(score=0.8, payload={"learning_text": "c"}, point_id="3"),
    ]
    broken_client = MagicMock()
    broken_client.messages.create.side_effect = Exception("haiku unreachable")
    out = applicability_filter(
        hits,
        anthropic_client=broken_client,
        diff_summary="some diff",
        keep_max=5,
    )
    # All 3 hits passed through unfiltered.
    assert [h.point_id for h in out] == ["1", "2", "3"]


def test_applicability_filter_keeps_yes_and_maybe_drops_no():
    """Happy path: Haiku verdicts route the hits."""
    from shared.learnings import applicability_filter

    hits = [
        Hit(score=0.9, payload={"learning_text": "a"}, point_id="1"),
        Hit(score=0.85, payload={"learning_text": "b"}, point_id="2"),
        Hit(score=0.8, payload={"learning_text": "c"}, point_id="3"),
    ]
    client = MagicMock()
    # Three calls, three verdicts: yes, no, maybe.
    msgs = [MagicMock(content=[MagicMock(text=v)]) for v in ("yes", "no", "Maybe.")]
    client.messages.create.side_effect = msgs
    out = applicability_filter(
        hits,
        anthropic_client=client,
        diff_summary="d",
        keep_max=5,
    )
    assert [h.point_id for h in out] == ["1", "3"]


def test_applicability_filter_respects_keep_max():
    """keep_max caps the kept set even when more hits would qualify."""
    from shared.learnings import applicability_filter

    hits = [
        Hit(score=0.9 - i * 0.01, payload={"learning_text": f"l{i}"}, point_id=str(i))
        for i in range(8)
    ]
    client = MagicMock()
    client.messages.create.side_effect = [
        MagicMock(content=[MagicMock(text="yes")]) for _ in range(8)
    ]
    out = applicability_filter(
        hits,
        anthropic_client=client,
        diff_summary="d",
        keep_max=3,
    )
    assert len(out) == 3
    assert [h.point_id for h in out] == ["0", "1", "2"]
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_phase6/test_shared_learnings.py -v`
Expected: ImportError on `shared.learnings`.

- [ ] **Step 3: Implement shared/learnings.py**

Create `shared/learnings.py`:

```python
"""Shared retrieval-side learnings module — used by BOTH reviewers.

Responsibilities (spec §3):
  - retrieve_for_diff(repo, chunks)        -> threshold-filtered hits
  - applicability_filter(hits, diff)        -> Haiku-judged subset
  - format_for_prompt(hits)                 -> <past_learnings> XML
  - search_tool_handler(query, repo, k)    -> <item ...> XML for the tool

Strictly additive: any failure returns an empty result so the reviewer
keeps running (spec §8).
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any, Protocol

from learnings.ast_chunker import Chunk
from learnings.qdrant_store import Hit, QdrantStore, collection_for


class Embedder(Protocol):
    def embed_one(self, text: str, *, input_type: str = "document") -> list[float]: ...


_INTRO = (
    "These are corrections previous maintainers have given for code with "
    "similar shape. Treat them as priors, not rules. If a learning clearly "
    "applies to a finding you're about to make, cite it; if it suggests a "
    "finding you'd otherwise miss, raise that finding. If it doesn't apply, "
    "ignore it silently."
)


def _cdata(text: str) -> str:
    """Wrap text in <![CDATA[...]]> safely. CDATA sections terminate on
    `]]>`; the standard escape splits the offending sequence across two
    sections so the parser sees the literal three characters."""
    return f"<![CDATA[{text.replace(']]>', ']]]]><![CDATA[>')}]]>"


def apply_threshold(hits: list[Hit], threshold: float) -> list[Hit]:
    return [h for h in hits if h.score >= threshold]


def retrieve_for_diff(
    *,
    repo: str,
    chunks: list[Chunk],
    store: QdrantStore,
    embedder: Embedder,
    collection_override: str | None = None,
    per_query_k: int = 5,
    threshold: float = 0.78,
) -> list[Hit]:
    """One embed + query per AST chunk; merge, dedupe, threshold."""
    collection = collection_override or collection_for(repo)
    by_id: dict[str, Hit] = {}
    for chunk in chunks:
        try:
            vec = embedder.embed_one(chunk.text, input_type="query")
            hits = store.search(collection, query_vector=vec, k=per_query_k)
        except Exception:
            continue  # fail-open per spec §8
        for h in hits:
            existing = by_id.get(h.point_id)
            if existing is None or h.score > existing.score:
                by_id[h.point_id] = h
    return apply_threshold(list(by_id.values()), threshold)


def applicability_filter(
    hits: list[Hit],
    *,
    anthropic_client: Any,
    diff_summary: str,
    model: str = "claude-haiku-4-5-20251001",
    keep_max: int = 5,
) -> list[Hit]:
    """Haiku judges each hit. Drop "no"; keep "yes" + "maybe". Spec §5.2.

    Returns up to ``keep_max`` hits, preserving original score order.

    Fail-open semantics (spec §8.2 — "Applicability filter (Haiku)
    failure → Skip filter; pass through threshold-only results"): if
    the Haiku call raises ANY exception, the whole filter step bails
    and returns ``hits[:keep_max]`` unfiltered. Per-hit fail-open
    would mix "Haiku said yes/maybe" with "Haiku threw — we don't know"
    in the output and silently consume the keep_max budget with
    un-judged hits.
    """
    if not hits:
        return []
    try:
        verdicts = [
            _judge_applicability(anthropic_client, model, diff_summary, h)
            for h in hits
        ]
    except Exception:
        return hits[:keep_max]
    return [h for h, v in zip(hits, verdicts) if v in ("yes", "maybe")][:keep_max]


def _judge_applicability(client: Any, model: str, diff_summary: str, hit: Hit) -> str:
    p = hit.payload
    prompt = (
        "Is the past learning below applicable to the diff hunk below?\n"
        "Answer EXACTLY one word: yes, no, or maybe.\n\n"
        f"PAST LEARNING:\n{p.get('learning_text','')}\n\n"
        f"PAST CODE ANCHOR ({p.get('file_path','')}:"
        f"{p.get('line_start','')}-{p.get('line_end','')}):\n"
        f"{p.get('code_chunk_text','')}\n\n"
        f"NEW DIFF SUMMARY:\n{diff_summary}\n\n"
        "Answer:"
    )
    msg = client.messages.create(
        model=model, max_tokens=8,
        messages=[{"role": "user", "content": prompt}],
    )
    word = (msg.content[0].text or "").strip().lower()
    if word.startswith("yes"):
        return "yes"
    if word.startswith("no"):
        return "no"
    return "maybe"


def format_for_prompt(hits: list[Hit]) -> str:
    if not hits:
        return ""
    items = "\n".join(_render_item(i + 1, h) for i, h in enumerate(hits))
    return f"<past_learnings>\n  <intro>\n    {_INTRO}\n  </intro>\n{items}\n</past_learnings>"


def _render_item(idx: int, h: Hit) -> str:
    p = h.payload
    return (
        f'  <item id="{idx}" score="{h.score:.2f}" '
        f'file="{escape(p.get("file_path",""), quote=True)}" '
        f'lines="{p.get("line_start","")}-{p.get("line_end","")}" '
        f'author="{escape(p.get("author",""), quote=True)}" '
        f'pr="{escape(p.get("repo",""), quote=True)}#{p.get("pr_number","")}" '
        f'captured="{escape(p.get("captured_at","")[:10], quote=True)}">\n'
        f"    <learning>{escape(p.get('learning_text',''))}</learning>\n"
        f'    <original_code language="{escape(p.get("language",""), quote=True)}">'
        f"{_cdata(p.get('code_chunk_text',''))}</original_code>\n"
        f"  </item>"
    )


def search_tool_handler(
    *, query: str, repo: str, store: QdrantStore, embedder: Embedder,
    collection_override: str | None = None, k: int = 5,
) -> str:
    """Body of the `search_learnings` tool. Returns an XML-fragment string."""
    collection = collection_override or collection_for(repo)
    try:
        vec = embedder.embed_one(query, input_type="query")
        hits = store.search(collection, query_vector=vec, k=k)
    except Exception:
        return "<results/>"
    if not hits:
        return "<results/>"
    items = "\n".join(_render_item(i + 1, h) for i, h in enumerate(hits))
    return f"<results>\n{items}\n</results>"
```

Verify ≤200 LOC:

```bash
wc -l shared/learnings.py
```

If over budget, split (e.g. move `applicability_filter` body into a private module).

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_phase6/test_shared_learnings.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add shared/learnings.py tests/test_phase6/test_shared_learnings.py
git commit -m "phase 6: shared/learnings.py — retrieve + format + applicability + tool handler"
```

---

## Task 8: Add the search_learnings tool surface (skill + nudge)

**Files:**
- Create: `shared/skills/learnings_search.md`
- Modify: `shared/prompts.py` — add one-line action_space nudge

- [ ] **Step 1: Create the progressive-disclosure skill**

Create `shared/skills/learnings_search.md`:

```markdown
# search_learnings — query formulation

Use this skill when you need to dig deeper than the auto-injected
`<past_learnings>` block. The block surfaces the top-K (5) maintainer
corrections matched to the diff at cosine ≥ 0.78. If you suspect a
relevant learning didn't surface, call `search_learnings(query)`.

## When to call

- A finding's category or pattern feels like something maintainers have
  taught before, but the auto-injected block didn't include a hit.
- You're uncertain whether a finding is real and want to check whether
  past corrections have addressed similar code.

## How to phrase the query

Pick the form that matches the *match shape* you want:

- **Exact code pattern** — paste the snippet (e.g. `Reflect.apply(fn, this, args)`).
  Best for syntactic similarities.
- **Natural-language description** — describe the concept (e.g.
  "OAuth state CSRF check missing"). Best for cross-language patterns
  and security/architectural concerns where syntactic match is brittle.
- **Hybrid** — short NL preamble followed by representative code.

## What you get back

An `<results>` block with the same `<item>` shape as the auto-injected
section: score, file, lines, author, learning text, code anchor. Treat
items the same way: priors, not rules.

## Don't

- Don't call this tool repeatedly with the same query.
- Don't search for things already in the auto-injected `<past_learnings>` block.
```

- [ ] **Step 2: Add the system-prompt nudge**

In `shared/prompts.py`, find the `<action_space>` section of `SYSTEM_PROMPT`. Add this bullet alongside the other tools (precise wording from spec §7.3):

```
- search_learnings(query): retrieve past maintainer corrections by free-text
  query. The system also auto-injects high-confidence past learnings into the
  user prompt under <past_learnings>; only call this tool if you need more.
```

(Use `Edit` with the existing `<action_space>` content; do not duplicate other bullets.)

- [ ] **Step 3: Verify the prompt change**

Run: `uv run python -c "from shared.prompts import SYSTEM_PROMPT; print('search_learnings' in SYSTEM_PROMPT)"`
Expected: `True`.

- [ ] **Step 4: Commit**

```bash
git add shared/skills/learnings_search.md shared/prompts.py
git commit -m "phase 6: search_learnings skill + system-prompt nudge"
```

---

## Task 9: Client SDK reviewer integration

**Files:**
- Modify: `client_sdk/reviewer.py`

The Client SDK reviewer must (a) build the `<past_learnings>` block before the API call, (b) register `search_learnings` in `ALL_TOOLS`, (c) route the tool call through `_dispatch_tool`.

- [ ] **Step 1: Read the current state**

Read `client_sdk/reviewer.py` end-to-end. Note:
- `ALL_TOOLS` definition around line 102
- `_dispatch_tool(repo, name, args)` around line 164
- `user_prompt = USER_PROMPT_TEMPLATE.format(...)` around line 266

- [ ] **Step 2: Add the search_learnings tool definition**

In `client_sdk/reviewer.py`, near where other tool dicts are defined (just before `ALL_TOOLS`), add:

```python
SEARCH_LEARNINGS_TOOL: dict[str, Any] = {
    "name": "search_learnings",
    "description": (
        "Search past maintainer corrections by free-text query. Use when "
        "the auto-injected <past_learnings> didn't surface something you "
        "suspect was previously taught. Returns top-5."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Code snippet OR natural-language description.",
            },
            "k": {"type": "integer", "default": 5, "maximum": 10},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}
```

Then update `ALL_TOOLS`:

```python
ALL_TOOLS: list[dict[str, Any]] = [
    *INVESTIGATION_TOOLS,
    SEARCH_LEARNINGS_TOOL,
    {**SUBMIT_FINDINGS_TOOL, "cache_control": CACHE_CONTROL_EPHEMERAL},
]
```

- [ ] **Step 3: Add learnings-aware prompt builder**

Add this helper near the top of the file (after imports):

```python
def _build_user_prompt_with_learnings(
    repo: Repo, base_ref: str, head_ref: str, repo_slug: str | None
) -> str:
    """Build the user prompt with an optional <past_learnings> block.

    Strictly additive: if any step fails or no learnings are configured,
    fall back to the plain USER_PROMPT_TEMPLATE — the reviewer keeps running.
    """
    base = USER_PROMPT_TEMPLATE.format(
        repo_path="<sandbox repo root>", base_ref=base_ref, head_ref=head_ref,
    )
    if not repo_slug:
        return base
    try:
        from learnings.config import load as load_cfg
        from learnings.ast_chunker import chunks_for_diff
        from learnings.voyage_client import VoyageClient
        from learnings.qdrant_store import QdrantStore
        from shared.learnings import (
            applicability_filter, format_for_prompt, retrieve_for_diff,
        )
        import anthropic

        cfg = load_cfg()
        # Diff → changed-line map. We use git diff against base_ref locally
        # via repo.exec; if the repo abstraction doesn't expose this we
        # fall back to no-learnings.
        diff_text = repo.exec(f"git diff {base_ref}..{head_ref}", timeout=30).stdout
        changed = _changed_line_map(diff_text)
        chunks = chunks_for_diff(repo.path if hasattr(repo, "path") else None, changed)
        if not chunks:
            return base
        store = QdrantStore(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key)
        embedder = VoyageClient(api_key=cfg.voyage_api_key)
        hits = retrieve_for_diff(
            repo=repo_slug, chunks=chunks, store=store, embedder=embedder,
            per_query_k=cfg.per_query_k, threshold=cfg.threshold,
        )
        if cfg.filter_enabled and hits:
            ant = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
            hits = applicability_filter(
                hits, anthropic_client=ant, diff_summary=diff_text[:2000],
                keep_max=cfg.top_k,
            )
        block = format_for_prompt(hits[: cfg.top_k])
        if not block:
            return base
        # Insert <past_learnings> AFTER <repository_context> and BEFORE <task>.
        # USER_PROMPT_TEMPLATE structure varies — append a separator block.
        return f"{base}\n\n{block}"
    except Exception:
        return base


def _changed_line_map(diff_text: str) -> dict[str, list[int]]:
    """Parse a unified-diff into {file_path: [right-side line numbers]}."""
    out: dict[str, list[int]] = {}
    cur: str | None = None
    line_no: int = 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ b/"):
            cur = raw[6:].strip()
            out.setdefault(cur, [])
        elif raw.startswith("@@"):
            # @@ -a,b +c,d @@ — pull `c`.
            try:
                rhs = raw.split("+")[1].split(" ")[0]
                line_no = int(rhs.split(",")[0])
            except Exception:
                line_no = 0
        elif cur and raw.startswith("+") and not raw.startswith("+++"):
            out[cur].append(line_no)
            line_no += 1
        elif cur and not raw.startswith("-"):
            line_no += 1
    return {k: v for k, v in out.items() if v}
```

- [ ] **Step 4: Wire the helper into `run()`**

Replace the existing `user_prompt = USER_PROMPT_TEMPLATE.format(...)` call (around line 266) with:

```python
    repo_slug = _infer_repo_slug(repo)
    user_prompt = _build_user_prompt_with_learnings(repo, base_ref, head_ref, repo_slug)
```

And add (before the helper):

```python
def _infer_repo_slug(repo: Repo) -> str | None:
    """Best-effort owner/name from `git remote get-url origin`."""
    try:
        url = repo.exec("git remote get-url origin", timeout=5).stdout.strip()
        # Accept https://github.com/x/y(.git) or git@github.com:x/y(.git)
        url = url.removesuffix(".git")
        if "github.com" not in url:
            return None
        path = url.split("github.com")[-1].lstrip("/:")
        parts = path.split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    except Exception:
        return None
    return None
```

- [ ] **Step 5: Add the search_learnings dispatch branch**

In `_dispatch_tool` (around line 164), add a branch:

```python
    if name == "search_learnings":
        try:
            from learnings.config import load as load_cfg
            from learnings.qdrant_store import QdrantStore
            from learnings.voyage_client import VoyageClient
            from shared.learnings import search_tool_handler

            cfg = load_cfg()
            slug = _infer_repo_slug(repo)
            if not slug:
                return "<results/>"
            return search_tool_handler(
                query=str(args.get("query", "")),
                repo=slug,
                store=QdrantStore(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key),
                embedder=VoyageClient(api_key=cfg.voyage_api_key),
                k=int(args.get("k", 5)),
            )
        except Exception as e:
            return f"<results error={str(e)!r}/>"
```

Place this branch BEFORE the `return f"Error: unknown tool {name!r}"` line.

- [ ] **Step 6: Run the existing reviewer regression test (no learnings seeded)**

Run: `uv run pytest tests/test_phase6/ -v` plus an existing fixture run via the project's smoke setup if available.

Expected: existing tests pass; the reviewer with NO learnings in the store produces identical findings to today's baseline (the layer is no-op-able — see spec §8).

- [ ] **Step 7: Commit**

```bash
git add client_sdk/reviewer.py
git commit -m "phase 6: client SDK reviewer — past_learnings block + search_learnings tool"
```

---

## Task 10: Agent SDK reviewer integration

**Files:**
- Modify: `agent_sdk/reviewer.py`

Mirror Task 9 but on the Agent SDK side. Adds `search_learnings` as an MCP tool on the in-process server and builds the same prompt block.

- [ ] **Step 1: Read the existing MCP setup**

Read `agent_sdk/reviewer.py:418-460` (the `create_sdk_mcp_server` block). Note the pattern: each tool is a function decorated/registered on the server; tools take a JSON dict, return a wrapped dict.

- [ ] **Step 2: Add the search_learnings MCP tool**

Inside `run()`, before `server = create_sdk_mcp_server(...)`, define:

```python
    @tool(
        "search_learnings",
        "Search past maintainer corrections by free-text query. Use when "
        "the auto-injected <past_learnings> didn't surface something you "
        "suspect was previously taught. Returns top-5.",
        {"query": str, "k": int},
    )
    async def _search_learnings(args: dict[str, Any]) -> dict[str, Any]:
        try:
            from learnings.config import load as load_cfg
            from learnings.qdrant_store import QdrantStore
            from learnings.voyage_client import VoyageClient
            from shared.learnings import search_tool_handler

            cfg = load_cfg()
            slug = _infer_repo_slug(repo)
            if not slug:
                return _wrap_text("<results/>")
            xml = search_tool_handler(
                query=str(args.get("query", "")),
                repo=slug,
                store=QdrantStore(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key),
                embedder=VoyageClient(api_key=cfg.voyage_api_key),
                k=int(args.get("k", 5)),
            )
            return _wrap_text(xml)
        except Exception as e:
            return _wrap_text(f"<results error={str(e)!r}/>")
```

Then add `_search_learnings` to the `tools=[...]` list passed to `create_sdk_mcp_server`.

- [ ] **Step 3: Build the user prompt with learnings**

Replace the `user_prompt = USER_PROMPT_TEMPLATE.format(...)` line (around line 446) with the same helper-based call as Client SDK. Copy `_build_user_prompt_with_learnings`, `_changed_line_map`, and `_infer_repo_slug` into `agent_sdk/reviewer.py` (or — preferred — extract them into a new helper module).

**Preferred refactor:** create `shared/learnings_prompt.py` containing `_build_user_prompt_with_learnings`, `_changed_line_map`, and `_infer_repo_slug`. Import from both reviewers. (Extracts duplicated code; keeps each reviewer's diff small.)

- [ ] **Step 4: Run the smoke regression**

Run the existing Agent SDK smoke / suite commands. Confirm reviewer behavior is unchanged with an empty learnings store.

- [ ] **Step 5: Commit**

```bash
git add agent_sdk/reviewer.py shared/learnings_prompt.py
git commit -m "phase 6: agent SDK reviewer — past_learnings block + search_learnings MCP tool"
```

---

## Task 11: GitHub adapter — extend pr_fetch.py

**Files:**
- Modify: `github/pr_fetch.py` — add `Comment` dataclass, `list_open_prs`, `list_pr_review_comments`
- Create: `tests/test_phase6/test_pr_fetch_extensions.py`

- [ ] **Step 1: Write failing tests for the new functions**

Create `tests/test_phase6/test_pr_fetch_extensions.py`:

```python
"""Tests for the Phase-6 contributions to github/pr_fetch.py."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from github.pr_fetch import (
    Comment,
    PullRequest,
    list_open_prs,
    list_pr_review_comments,
)


def _fake_subprocess(stdout: str, returncode: int = 0):
    """Helper: build a CompletedProcess-shaped mock."""
    cp = MagicMock()
    cp.stdout = stdout
    cp.returncode = returncode
    return cp


def test_list_open_prs_returns_dataclasses():
    fake = [
        {
            "number": 1, "title": "T1",
            "html_url": "https://github.com/o/r/pull/1",
            "base": {"sha": "b1"}, "head": {"sha": "h1"},
            "updated_at": "2026-05-03T10:00:00Z",
        },
        {
            "number": 2, "title": "T2",
            "html_url": "https://github.com/o/r/pull/2",
            "base": {"sha": "b2"}, "head": {"sha": "h2"},
            "updated_at": "2026-05-03T11:00:00Z",
        },
    ]
    with patch("github.pr_fetch._gh_json_paginated", return_value=fake):
        prs = list_open_prs("o/r")
    assert len(prs) == 2
    assert prs[0].owner == "o" and prs[0].repo == "r" and prs[0].number == 1


def test_list_open_prs_filters_by_since():
    fake = [
        {"number": 1, "title": "old", "html_url": "https://github.com/o/r/pull/1",
         "base": {"sha": "b"}, "head": {"sha": "h"}, "updated_at": "2026-04-01T10:00:00Z"},
        {"number": 2, "title": "new", "html_url": "https://github.com/o/r/pull/2",
         "base": {"sha": "b"}, "head": {"sha": "h"}, "updated_at": "2026-05-03T10:00:00Z"},
    ]
    with patch("github.pr_fetch._gh_json_paginated", return_value=fake):
        prs = list_open_prs("o/r", since="2026-05-01T00:00:00Z")
    assert [p.number for p in prs] == [2]


def test_list_pr_review_comments_returns_dataclasses():
    fake = [
        {
            "id": 1234567, "path": "src/foo.py", "line": 42,
            "start_line": None, "body": "@Working-Ant learn x",
            "user": {"login": "alice"}, "created_at": "2026-05-03T10:00:00Z",
        },
        {
            "id": 1234568, "path": "src/bar.py", "line": 99,
            "start_line": 95, "body": "lgtm",
            "user": {"login": "bob"}, "created_at": "2026-05-03T11:00:00Z",
        },
    ]
    pr = PullRequest(owner="o", repo="r", number=1, base_sha="b", head_sha="h",
                     title="t", html_url="https://github.com/o/r/pull/1")
    with patch("github.pr_fetch._gh_json_paginated", return_value=fake):
        cs = list_pr_review_comments(pr)
    assert len(cs) == 2
    assert cs[0].comment_id == 1234567
    assert cs[0].file_path == "src/foo.py"
    assert cs[0].line_start == 42 and cs[0].line_end == 42
    assert cs[1].line_start == 95 and cs[1].line_end == 99


def test_list_pr_review_comments_filters_since_id():
    fake = [
        {"id": 100, "path": "a", "line": 1, "start_line": None, "body": "x",
         "user": {"login": "a"}, "created_at": "2026-05-03T09:00:00Z"},
        {"id": 200, "path": "b", "line": 2, "start_line": None, "body": "y",
         "user": {"login": "a"}, "created_at": "2026-05-03T10:00:00Z"},
    ]
    pr = PullRequest(owner="o", repo="r", number=1, base_sha="b", head_sha="h",
                     title="t", html_url="https://github.com/o/r/pull/1")
    with patch("github.pr_fetch._gh_json_paginated", return_value=fake):
        cs = list_pr_review_comments(pr, since_id=100)
    assert [c.comment_id for c in cs] == [200]
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_phase6/test_pr_fetch_extensions.py -v`
Expected: ImportError on `Comment`, `list_open_prs`, `list_pr_review_comments`.

- [ ] **Step 3: Add Comment dataclass + functions**

Append to `github/pr_fetch.py`:

```python
@dataclass(frozen=True)
class Comment:
    """A PR review comment anchored to a file + line range."""
    comment_id: int
    file_path: str
    line_start: int       # 1-indexed; equals line_end for single-line
    line_end: int
    body: str
    author: str
    created_at: str       # ISO-8601


def list_open_prs(owner_repo: str, *, since: str | None = None) -> list[PullRequest]:
    """List open PRs in `owner/repo`. Optional `since` is ISO-8601;
    PRs with `updated_at < since` are filtered out client-side."""
    raw = _gh_json_paginated(f"repos/{owner_repo}/pulls?state=open&per_page=100")
    owner, repo = owner_repo.split("/", 1)
    out: list[PullRequest] = []
    for item in raw:
        if since and item.get("updated_at", "") < since:
            continue
        out.append(PullRequest(
            owner=owner, repo=repo, number=int(item["number"]),
            base_sha=item["base"]["sha"], head_sha=item["head"]["sha"],
            title=item["title"], html_url=item["html_url"],
        ))
    return out


def list_pr_review_comments(pr: PullRequest, *, since_id: int | None = None) -> list[Comment]:
    """List review comments on a PR. Optional `since_id` filters out
    comment ids ≤ since_id (matches our cursor semantics)."""
    raw = _gh_json_paginated(
        f"repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/comments?per_page=100"
    )
    out: list[Comment] = []
    for item in raw:
        cid = int(item["id"])
        if since_id is not None and cid <= since_id:
            continue
        line = int(item.get("line") or 0)
        start = int(item.get("start_line") or line)
        out.append(Comment(
            comment_id=cid,
            file_path=item.get("path", ""),
            line_start=start,
            line_end=line,
            body=item.get("body", ""),
            author=(item.get("user") or {}).get("login", ""),
            created_at=item.get("created_at", ""),
        ))
    return out
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_phase6/test_pr_fetch_extensions.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add github/pr_fetch.py tests/test_phase6/test_pr_fetch_extensions.py
git commit -m "phase 6: github/pr_fetch — Comment + list_open_prs + list_pr_review_comments"
```

---

## Task 12: GitHub adapter facade

**Files:**
- Create: `learnings/github_adapter.py`
- Create: `tests/test_phase6/test_github_adapter.py`

The adapter is a thin facade that wraps Phase 5's `github/pr_fetch.py` so the capture pipeline depends on a single Phase-6-shaped interface (easier to swap for testing or future Phase 4 / Daytona changes).

- [ ] **Step 1: Write failing test**

Create `tests/test_phase6/test_github_adapter.py`:

```python
"""Adapter wraps github/pr_fetch.py for the capture pipeline."""
from __future__ import annotations

from unittest.mock import patch

from github.pr_fetch import Comment, PullRequest
from learnings.github_adapter import GitHubAdapter


def test_adapter_delegates_list_open_prs():
    fake_prs = [PullRequest(owner="o", repo="r", number=1, base_sha="b",
                            head_sha="h", title="t", html_url="u")]
    with patch("learnings.github_adapter.list_open_prs", return_value=fake_prs) as m:
        a = GitHubAdapter()
        out = a.list_open_prs("o/r", since="2026-01-01T00:00:00Z")
        assert out == fake_prs
        m.assert_called_once_with("o/r", since="2026-01-01T00:00:00Z")


def test_adapter_delegates_list_pr_review_comments():
    pr = PullRequest(owner="o", repo="r", number=1, base_sha="b",
                     head_sha="h", title="t", html_url="u")
    fake = [Comment(comment_id=1, file_path="f", line_start=1, line_end=1,
                    body="b", author="a", created_at="t")]
    with patch("learnings.github_adapter.list_pr_review_comments", return_value=fake) as m:
        a = GitHubAdapter()
        out = a.list_pr_review_comments(pr, since_id=10)
        assert out == fake
        m.assert_called_once_with(pr, since_id=10)
```

- [ ] **Step 2: Run test, verify it fails**

Run: `uv run pytest tests/test_phase6/test_github_adapter.py -v`
Expected: ImportError on `learnings.github_adapter`.

- [ ] **Step 3: Implement github_adapter.py**

Create `learnings/github_adapter.py`:

```python
"""Phase-6-shaped facade over Phase 5's github/pr_fetch.py.

Wrapping keeps the capture pipeline's GitHub dependency narrow (one
interface) and gives us a single swap point for future changes — e.g.
Phase 4 / Daytona moving the clone path off the host.
"""
from __future__ import annotations

from github.pr_fetch import (
    Comment,
    PullRequest,
    list_open_prs,
    list_pr_review_comments,
)


class GitHubAdapter:
    """Thin synchronous facade — capture daemon's only GitHub seam."""

    def list_open_prs(self, owner_repo: str, *, since: str | None = None) -> list[PullRequest]:
        return list_open_prs(owner_repo, since=since)

    def list_pr_review_comments(
        self, pr: PullRequest, *, since_id: int | None = None
    ) -> list[Comment]:
        return list_pr_review_comments(pr, since_id=since_id)
```

- [ ] **Step 4: Run test, verify it passes**

Run: `uv run pytest tests/test_phase6/test_github_adapter.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add learnings/github_adapter.py tests/test_phase6/test_github_adapter.py
git commit -m "phase 6: github_adapter facade over pr_fetch.py"
```

---

## Task 13: Capture pipeline — one-shot mode

**Files:**
- Create: `learnings/capture.py`
- Create: `tests/test_phase6/test_capture.py`

This is the daemon's body. One iteration of the loop is the unit; `--watch` just runs it forever.

- [ ] **Step 1: Write failing test (one-shot mode, mocked external deps)**

Create `tests/test_phase6/test_capture.py`:

```python
"""Capture pipeline — one iteration is the unit. --watch loops it."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from github.pr_fetch import Comment, PullRequest
from learnings.capture import capture_once


def _pr(number: int = 1) -> PullRequest:
    return PullRequest(
        owner="o", repo="r", number=number, base_sha="b", head_sha="h",
        title="t", html_url=f"https://github.com/o/r/pull/{number}",
    )


def _comment(cid: int, body: str = "@Working-Ant learn always X",
             file_path: str = "tiny_module.py", line: int = 6) -> Comment:
    return Comment(
        comment_id=cid, file_path=file_path,
        line_start=line, line_end=line, body=body,
        author="alice", created_at="2026-05-03T10:00:00Z",
    )


def test_capture_once_skips_when_no_mention(tmp_path):
    adapter = MagicMock()
    adapter.list_open_prs.return_value = [_pr()]
    adapter.list_pr_review_comments.return_value = [_comment(1, body="LGTM")]
    embedder = MagicMock()
    store = MagicMock()
    with patch("learnings.capture.chunk_for_anchor") as ck:
        capture_once(
            repo="o/r", adapter=adapter, embedder=embedder, store=store,
            state_path=tmp_path / "state.json", repo_clone_root=tmp_path,
            handle="@Working-Ant", call_words=("learn",),
        )
    embedder.embed_one.assert_not_called()
    store.upsert.assert_not_called()
    ck.assert_not_called()


def test_capture_once_processes_mention_end_to_end(tmp_path):
    adapter = MagicMock()
    adapter.list_open_prs.return_value = [_pr()]
    adapter.list_pr_review_comments.return_value = [_comment(1)]
    embedder = MagicMock()
    embedder.embed_one.return_value = [0.1] * 1024
    store = MagicMock()

    # Materialize a real source file the chunker will read.
    src = tmp_path / "tiny_module.py"
    src.write_text("def first_function(x):\n    return x + 1\n")

    with patch("learnings.capture._ensure_clone", return_value=tmp_path):
        capture_once(
            repo="o/r", adapter=adapter, embedder=embedder, store=store,
            state_path=tmp_path / "state.json", repo_clone_root=tmp_path,
            handle="@Working-Ant", call_words=("learn",),
        )
    embedder.embed_one.assert_called_once()
    store.upsert.assert_called_once()
    args, kwargs = store.upsert.call_args
    payload = kwargs["payload"]
    assert payload.learning_text == "always X"
    assert payload.repo == "o/r"
    assert payload.author == "alice"


def test_capture_once_advances_cursor_after_success(tmp_path):
    state_path = tmp_path / "state.json"
    adapter = MagicMock()
    adapter.list_open_prs.return_value = [_pr()]
    adapter.list_pr_review_comments.return_value = [_comment(42)]
    embedder = MagicMock(); embedder.embed_one.return_value = [0.1] * 1024
    store = MagicMock()

    src = tmp_path / "tiny_module.py"
    src.write_text("def first_function(x):\n    return x + 1\n")

    with patch("learnings.capture._ensure_clone", return_value=tmp_path):
        capture_once(
            repo="o/r", adapter=adapter, embedder=embedder, store=store,
            state_path=state_path, repo_clone_root=tmp_path,
            handle="@Working-Ant", call_words=("learn",),
        )
    import json
    assert json.loads(state_path.read_text())["o/r"] == 42


def test_capture_once_fails_open_on_per_comment_error(tmp_path):
    """A bad comment must not abort the whole iteration."""
    adapter = MagicMock()
    adapter.list_open_prs.return_value = [_pr()]
    adapter.list_pr_review_comments.return_value = [
        _comment(1, file_path="missing.py", line=999),  # bad anchor
        _comment(2, file_path="tiny_module.py", line=1),  # good anchor
    ]
    embedder = MagicMock(); embedder.embed_one.return_value = [0.1] * 1024
    store = MagicMock()

    src = tmp_path / "tiny_module.py"
    src.write_text("def first_function(x):\n    return x + 1\n")

    with patch("learnings.capture._ensure_clone", return_value=tmp_path):
        capture_once(
            repo="o/r", adapter=adapter, embedder=embedder, store=store,
            state_path=tmp_path / "state.json", repo_clone_root=tmp_path,
            handle="@Working-Ant", call_words=("learn",),
        )
    # Both comments processed — store called once for the good one.
    assert store.upsert.call_count == 1
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_phase6/test_capture.py -v`
Expected: ImportError on `learnings.capture`.

- [ ] **Step 3: Implement capture.py (one-shot only — daemon mode in Task 14)**

Create `learnings/capture.py`:

```python
"""Capture pipeline — single-iteration body.

`capture_once` runs ONE poll cycle: list open PRs → list review
comments since cursor → for each mention, chunk the anchor + embed +
upsert. `capture_watch` loops `capture_once` forever. `main` is the CLI.

Failure isolation per spec §8.1: per-comment errors are logged + skipped
with the cursor advancing past them; per-PR errors don't abort the loop.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from github.pr_fetch import Comment, PullRequest

from learnings.ast_chunker import chunk_for_anchor
from learnings.config import load as load_config
from learnings.extractor import Extractor, Mention
from learnings.github_adapter import GitHubAdapter
from learnings.qdrant_store import (
    LearningPayload,
    QdrantStore,
    collection_for,
    point_id_for,
)
from learnings.state import State
from learnings.voyage_client import VoyageClient

log = logging.getLogger("learnings.capture")

DEFAULT_STATE_PATH = Path("shared/memory/learnings_state.json")
DEFAULT_CLONE_ROOT = Path("/tmp/learnings_clones")


def _ensure_clone(repo: str, head_sha: str, root: Path) -> Path:
    """Ensure a local checkout of `repo` at `head_sha`. Returns the
    checkout path. Reuses an existing clone if present."""
    target = root / repo.replace("/", "__")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        import subprocess
        subprocess.run(
            ["gh", "repo", "clone", repo, str(target)],
            check=True, capture_output=True, timeout=120,
        )
    import subprocess
    subprocess.run(
        ["git", "-C", str(target), "fetch", "origin", head_sha],
        check=True, capture_output=True, timeout=60,
    )
    subprocess.run(
        ["git", "-C", str(target), "checkout", head_sha],
        check=True, capture_output=True, timeout=30,
    )
    return target


def _process_comment(
    *, repo: str, pr: PullRequest, comment: Comment, mention: Mention,
    embedder: VoyageClient, store: QdrantStore, repo_clone_root: Path,
) -> None:
    clone = _ensure_clone(repo, pr.head_sha, repo_clone_root)
    src = clone / comment.file_path
    chunk = chunk_for_anchor(
        src, line_start=comment.line_start, line_end=comment.line_end
    )
    vec = embedder.embed_one(chunk.text, input_type="document")
    payload = LearningPayload(
        code_chunk_text=chunk.text,
        learning_text=mention.text,
        repo=repo,
        pr_number=pr.number,
        file_path=comment.file_path,
        line_start=chunk.line_start,
        line_end=chunk.line_end,
        chunk_kind=chunk.kind,
        language="python",
        author=comment.author,
        captured_at=datetime.now(timezone.utc).isoformat(),
        commit_sha=pr.head_sha,
    )
    store.upsert(
        collection_for(repo),
        point_id=point_id_for(repo, comment.comment_id),
        vector=vec, payload=payload,
    )


def capture_once(
    *, repo: str, adapter: GitHubAdapter, embedder: VoyageClient,
    store: QdrantStore, state_path: Path, repo_clone_root: Path,
    handle: str, call_words: tuple[str, ...],
) -> None:
    """One iteration of the capture loop."""
    state = State(state_path)
    extractor = Extractor(handle=handle, call_words=call_words)
    cursor = state.cursor(repo)

    try:
        prs = adapter.list_open_prs(repo)
    except Exception as e:
        log.warning("list_open_prs failed for %s: %s", repo, e)
        return

    for pr in prs:
        try:
            comments = adapter.list_pr_review_comments(pr, since_id=cursor)
        except Exception as e:
            log.warning("list_pr_review_comments failed for #%d: %s", pr.number, e)
            continue
        for c in comments:
            mention = extractor.parse(c.body)
            try:
                if mention is not None:
                    _process_comment(
                        repo=repo, pr=pr, comment=c, mention=mention,
                        embedder=embedder, store=store,
                        repo_clone_root=repo_clone_root,
                    )
                state.advance(repo, c.comment_id)
            except Exception as e:
                log.warning(
                    "comment %d (#%d) processing failed: %s — advancing past it",
                    c.comment_id, pr.number, e,
                )
                state.advance(repo, c.comment_id)


def capture_watch(*, interval_s: int, **kwargs) -> None:
    log.info("capture daemon starting; interval=%ds", interval_s)
    while True:
        try:
            capture_once(**kwargs)
        except Exception as e:
            log.exception("capture iteration crashed: %s", e)
        time.sleep(interval_s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="learnings.capture")
    p.add_argument("--repo", required=True, help="owner/name")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--once", action="store_true")
    g.add_argument("--watch", action="store_true")
    p.add_argument("--interval", type=int, default=None,
                   help="seconds between polls in --watch mode (overrides env)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    embedder = VoyageClient(api_key=cfg.voyage_api_key)
    store = QdrantStore(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key)
    adapter = GitHubAdapter()

    common = dict(
        repo=args.repo, adapter=adapter, embedder=embedder, store=store,
        state_path=DEFAULT_STATE_PATH, repo_clone_root=DEFAULT_CLONE_ROOT,
        handle=cfg.handle, call_words=cfg.call_words,
    )

    if args.once:
        capture_once(**common)
    else:
        capture_watch(interval_s=args.interval or cfg.interval_s, **common)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_phase6/test_capture.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add learnings/capture.py tests/test_phase6/test_capture.py
git commit -m "phase 6: capture pipeline — one-shot + daemon mode + cli"
```

---

## Task 14: Demo launcher

**Files:**
- Create: `scripts/demo.py`

The launcher is a thin process supervisor: spawn the capture daemon as a subprocess, run the reviewer in the foreground, propagate Ctrl-C to both. No tests — this is plumbing.

- [ ] **Step 1: Implement scripts/demo.py**

Create `scripts/demo.py`:

```python
"""Phase 6 demo launcher.

Spawns the capture daemon as a background subprocess and runs the
reviewer in the foreground against a target PR. Ctrl-C in the primary
terminal cleanly shuts down both. Use `--rerun` (no daemon spawn) in a
second terminal to re-review a PR while the original session's daemon
keeps polling.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def _spawn_daemon(repo: str, interval: int) -> subprocess.Popen[bytes]:
    print(f"[demo] starting capture daemon for {repo} (interval={interval}s)")
    p = subprocess.Popen(
        [sys.executable, "-m", "learnings.capture",
         "--repo", repo, "--watch", "--interval", str(interval)],
        # Daemon lives in its own process group so Ctrl-C in the parent
        # doesn't double-signal.
        preexec_fn=os.setpgrp,
    )
    time.sleep(2.0)  # let the daemon settle past its first poll
    return p


def _run_reviewer(repo: str, pr_number: int) -> int:
    """Drive the existing Phase 5 review_pr.py CLI."""
    pr_url = f"https://github.com/{repo}/pull/{pr_number}"
    print(f"[demo] running reviewer on {pr_url}")
    return subprocess.call(
        [sys.executable, "scripts/github/review_pr.py", pr_url]
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="scripts/demo.py")
    p.add_argument("--repo", required=True, help="owner/name")
    p.add_argument("--pr", type=int, required=True, help="PR number")
    p.add_argument("--interval", type=int, default=60,
                   help="capture daemon poll interval in seconds")
    p.add_argument("--rerun", action="store_true",
                   help="skip daemon spawn (use when one is already running elsewhere)")
    args = p.parse_args(argv)

    daemon: subprocess.Popen[bytes] | None = None
    if not args.rerun:
        daemon = _spawn_daemon(args.repo, args.interval)

    try:
        return _run_reviewer(args.repo, args.pr)
    finally:
        if daemon is not None:
            print("[demo] stopping capture daemon")
            try:
                os.killpg(os.getpgid(daemon.pid), signal.SIGTERM)
                daemon.wait(timeout=5)
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test the launcher**

Run (will only fully exercise if env + a real PR is available):

```bash
uv run python scripts/demo.py --repo Hendrik040/code-review-agent --pr 1 --interval 30
```

Expected: spawns daemon, prints "running reviewer on …", reviewer runs (or fails clean if PR doesn't exist). Ctrl-C terminates both.

- [ ] **Step 3: Commit**

```bash
git add scripts/demo.py
git commit -m "phase 6: demo launcher — spawns daemon + reviewer, propagates SIGINT"
```

---

## Task 15: Live integration test

**Files:**
- Create: `tests/test_phase6/test_integration_live.py`

Gated behind `--live`. Validates the load-bearing pitch path: seed a learning, run the reviewer-side prompt build, assert the learning appears in the prompt block.

- [ ] **Step 1: Write the live integration test**

Create `tests/test_phase6/test_integration_live.py`:

```python
"""End-to-end live test. Requires --live + .env configured.

Asserts the headline pitch: seed a learning into Qdrant, then run the
retrieve-→-format pipeline against a hand-crafted diff, and verify the
learning surfaces in the <past_learnings> block.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from learnings.ast_chunker import Chunk
from learnings.qdrant_store import (
    LearningPayload,
    QdrantStore,
    collection_for,
    point_id_for,
)
from learnings.voyage_client import VoyageClient
from shared.learnings import format_for_prompt, retrieve_for_diff


@pytest.mark.live
def test_seed_then_retrieve_surfaces_learning(qdrant_test_collection, cfg):
    client, name = qdrant_test_collection
    store = QdrantStore.from_client(client)
    embedder = VoyageClient(api_key=cfg.voyage_api_key)

    code_text = (
        "def reflect_apply(fn, args):\n"
        "    return Reflect.apply(fn, this, args)\n"
    )
    seed_vec = embedder.embed_one(code_text, input_type="document")

    store.upsert(
        name,
        point_id=point_id_for("owner/repo", 1),
        vector=seed_vec,
        payload=LearningPayload(
            code_chunk_text=code_text,
            learning_text="Always use .$apply instead of Reflect.apply in this codebase.",
            repo="owner/repo", pr_number=22338,
            file_path="src/foo.ts", line_start=1, line_end=2,
            chunk_kind="function", language="typescript",
            author="alice",
            captured_at=datetime.now(timezone.utc).isoformat(),
            commit_sha="abc",
        ),
    )

    # Query with a structurally similar snippet.
    query_chunk = Chunk(
        text=(
            "def helper(fn, args):\n"
            "    return Reflect.apply(fn, this, args)\n"
        ),
        kind="function", line_start=1, line_end=2,
    )
    hits = retrieve_for_diff(
        repo="owner/repo", chunks=[query_chunk],
        store=store, embedder=embedder, collection_override=name,
        per_query_k=5, threshold=0.78,
    )
    assert hits, "expected at least one hit above threshold"
    block = format_for_prompt(hits)
    assert "Reflect.apply" in block
    assert "Always use .$apply" in block
```

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest tests/test_phase6/test_integration_live.py -v --live`
Expected: 1 passed (slow — real Voyage + Qdrant).

If retrieval threshold is too aggressive and the test fails, lower `LEARNINGS_THRESHOLD` for this run via `LEARNINGS_THRESHOLD=0.6 uv run pytest …` and open a follow-up to recalibrate (per spec §13).

- [ ] **Step 3: Commit**

```bash
git add tests/test_phase6/test_integration_live.py
git commit -m "phase 6: live integration test — seed→retrieve→format end-to-end"
```

---

## Final checklist

- [ ] All previous tasks completed and committed.
- [ ] `wc -l learnings/*.py shared/learnings.py` — every file ≤ 200 lines.
- [ ] `uv run pytest tests/test_phase6/ -v` — all unit tests pass without `--live`.
- [ ] `uv run pytest tests/test_phase6/ -v --live` — all tests including integration pass.
- [ ] Run the full project suite to confirm no regressions on existing fixtures: `uv run pytest -v` (excluding `--live` to avoid burning API credits in CI).
- [ ] Open PR against `main`. CR auto-review fires; triage per `.claude/agents/coderabbit-triage.md` (Critical/Major fix in-PR, nits reply-only).
- [ ] Update `docs/PLAN.md` Phase 6 section to reflect what shipped (post-merge, in a follow-up commit).

---

## Notes for the executing engineer

- **Read the spec first**: `docs/superpowers/specs/2026-05-03-phase-6-learnings-vectordb-design.md`. This plan implements that spec; if a spec line conflicts with a plan step, the spec wins — surface the conflict.
- **The 200-LOC rule is load-bearing.** If a file is creeping over, split it before exceeding. Don't justify exceptions.
- **Strict additivity**: any failure in this layer must NOT block the reviewer. The capture-side and retrieval-side both have try/except gates around external calls. Don't remove them.
- **Tests use real Qdrant Cloud** (per user direction). Keep test collections prefixed `test__` so they're easy to bulk-clean if something leaks. Free tier handles the load.
- **Don't touch the existing reviewer findings** in regression mode. With an empty learnings store, the reviewer must produce identical output to the pre-Phase-6 baseline. If a fixture's findings change, something is wrong with the additive guarantee — investigate before merging.
- **The launcher uses Phase 5's `scripts/github/review_pr.py`** for the reviewer side. If Phase 5 changes that script's CLI, update `scripts/demo.py` accordingly.
