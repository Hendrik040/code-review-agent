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
    # NEW (Phase 6.1): bot's parent review comment when this learning is a
    # reply, "" otherwise. Last so existing positional construction keeps
    # working (dataclass default-after-positional rules).
    bug_context: str = ""


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
