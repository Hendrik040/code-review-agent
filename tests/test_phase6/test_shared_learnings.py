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
