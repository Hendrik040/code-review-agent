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
