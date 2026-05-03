"""Phase 6 test fixtures.

Uses live Qdrant Cloud with random per-test collections (per spec §9 —
no in-memory mode). Tests are gated by env vars so CI can skip them
gracefully if credentials aren't configured.
"""
from __future__ import annotations

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
