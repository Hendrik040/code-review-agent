"""End-to-end live test. Requires --live + .env configured.

Asserts the headline pitch: seed a learning into Qdrant, then run the
retrieve-→-format pipeline against a hand-crafted diff, and verify the
learning surfaces in the <past_learnings> block.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from learnings.ast_chunker import Chunk
from learnings.qdrant_store import (
    LearningPayload,
    QdrantStore,
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
