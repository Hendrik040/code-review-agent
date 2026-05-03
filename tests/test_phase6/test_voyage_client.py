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
