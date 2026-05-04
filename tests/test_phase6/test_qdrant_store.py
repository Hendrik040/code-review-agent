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
