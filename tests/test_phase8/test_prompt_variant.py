"""Phase 8 — the reviewer prompt says the context is trimmed (default since 2026-11-27).

REVIEW_PROMPT_VARIANT=default restores the earlier prompt, so older sweeps
stay reproducible. The variant is read once, at import.
"""
from __future__ import annotations

import importlib

import pytest

import shared.prompts as prompts

TRIMMED = "The context is a trimmed selection"
OLD = "If the returned context contains enough evidence, submit\nfindings without further investigation."
NOT_SPECULATIVE = "is not speculative: report it"


def _load(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("REVIEW_PROMPT_VARIANT", raising=False)
    else:
        monkeypatch.setenv("REVIEW_PROMPT_VARIANT", value)
    return importlib.reload(prompts)


@pytest.fixture(autouse=True)
def _restore():
    yield
    importlib.reload(prompts)


@pytest.mark.parametrize("value", [None, "", "verify", "VERIFY", "something-else"])
def test_verify_prompt_is_the_default(monkeypatch, value):
    p = _load(monkeypatch, value)
    assert TRIMMED in p.SYSTEM_PROMPT and NOT_SPECULATIVE in p.SYSTEM_PROMPT
    assert OLD not in p.SYSTEM_PROMPT
    assert p.SYSTEM_PROMPT == p.SYSTEM_PROMPT_VERIFY


@pytest.mark.parametrize("value", ["default", "Default", "legacy"])
def test_old_prompt_on_request(monkeypatch, value):
    p = _load(monkeypatch, value)
    assert OLD in p.SYSTEM_PROMPT and TRIMMED not in p.SYSTEM_PROMPT
    assert p.SYSTEM_PROMPT == p.SYSTEM_PROMPT_LEGACY


def test_only_the_two_passages_differ(monkeypatch):
    p = _load(monkeypatch, None)
    restored = p.SYSTEM_PROMPT_VERIFY.replace(p._VERIFY, p._ENOUGH_EVIDENCE).replace(p._NOT_SPECULATIVE, p._SPECULATIVE)
    assert restored == p.SYSTEM_PROMPT_LEGACY
