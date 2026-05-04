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
