"""Agent SDK reviewer defaults: model and effort, the router's deep tier,
run-number reservation, and the opt-in reporting prompt.

No network and no model call: these only read module constants and call
small helpers.
"""
from __future__ import annotations

import threading

import pytest

import pricing
from agent_sdk import reviewer
from shared import routing


def test_default_model_is_opus_5_5_at_high_effort():
    assert (reviewer.MODEL, reviewer.EFFORT) == ("claude-opus-5-5", "high")


def test_router_deep_tier_is_the_reviewer_default(monkeypatch):
    monkeypatch.setattr(routing, "load_dotenv", lambda **_: None)
    for name in ("ROUTER_TIER_LIGHT", "ROUTER_TIER_STANDARD", "ROUTER_TIER_DEEP"):
        monkeypatch.delenv(name, raising=False)
    tiers = routing.load_tiers(routing.Tier("deep", reviewer.MODEL, reviewer.EFFORT))
    assert [(t.name, t.model, t.effort) for t in tiers] == [
        ("light", "claude-haiku-5-5", "medium"),
        ("standard", "claude-sonnet-5-5", "high"),
        ("deep", "claude-opus-5-5", "high"),
    ]


def test_default_model_has_a_price_row():
    """The result header prices a run at its model; no row means 'n/a'."""
    assert reviewer.MODEL in pricing.RATES


def test_reserved_run_ids_are_unique_across_threads(tmp_path, monkeypatch):
    monkeypatch.setattr(reviewer, "TRACES_DIR", tmp_path)
    (tmp_path / "run_007.txt").write_text("")
    got: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(32)

    def worker() -> None:
        barrier.wait()
        run_id = reviewer._reserve_run_id()
        with lock:
            got.append(run_id)

    threads = [threading.Thread(target=worker) for _ in range(32)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(got) == list(range(8, 40))
    assert all((tmp_path / f"run_{i:03d}.txt").exists() for i in got)


def test_next_run_id_only_peeks(tmp_path, monkeypatch):
    """compare.py calls _next_run_id() to pick a shared number; it must
    not leave a reserved file behind."""
    monkeypatch.setattr(reviewer, "TRACES_DIR", tmp_path)
    assert reviewer._next_run_id() == 1
    assert reviewer._next_run_id() == 1
    assert list(tmp_path.iterdir()) == []


def test_prompt_is_unchanged_without_a_variant(monkeypatch):
    monkeypatch.delenv("REVIEW_PROMPT_VARIANT", raising=False)
    assert reviewer.system_prompt() == reviewer.SYSTEM_PROMPT_AGENT_SDK
    assert "<reporting_note>" not in reviewer.system_prompt()


def test_file_considered_variant_adds_the_reporting_note(monkeypatch):
    monkeypatch.setenv("REVIEW_PROMPT_VARIANT", "file_considered")
    prompt = reviewer.system_prompt()
    assert prompt.startswith(reviewer.SYSTEM_PROMPT_AGENT_SDK)
    assert "<reporting_note>" in prompt
    assert "belongs in submit_findings" in prompt


def test_unknown_prompt_variant_is_an_error(monkeypatch):
    monkeypatch.setenv("REVIEW_PROMPT_VARIANT", "bogus")
    with pytest.raises(ValueError, match="REVIEW_PROMPT_VARIANT"):
        reviewer.system_prompt()
