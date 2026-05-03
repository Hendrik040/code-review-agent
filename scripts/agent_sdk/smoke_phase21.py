"""Smoke test for Phase 2.1 — exercises agent_sdk/reviewer.py end to end.

Mirrors scripts/client_sdk/smoke_phase16.py:
  Test A: structural / no-API checks (free, deterministic)
  Test B: one real API call driving the Agent SDK harness on the
          contract_mismatch fixture; asserts the loop submits findings
          and the return dict has the parity shape.

Run:    uv run python scripts/agent_sdk/smoke_phase21.py
Cost:   Test A free. Test B ~$0.10-0.30.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Project root on path. This file is at scripts/agent_sdk/ — three hops up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent_sdk import reviewer
from shared.findings import Finding, SUBMIT_FINDINGS_TOOL_NAME
from shared.fixtures import CONTRACT_MISMATCH, materialize
from shared.prompts import SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Test A — structural checks (deterministic, no API)
# ---------------------------------------------------------------------------


def test_a_structure() -> None:
    print("=== Test A: structural / no-API checks ===")

    # 1. Module imports cleanly.
    assert hasattr(reviewer, "run"), "reviewer.run is missing"
    assert hasattr(reviewer, "_run_async"), "reviewer._run_async is missing"
    print("  [ok] module imports + has expected entrypoints")

    # 2. SYSTEM_PROMPT_AGENT_SDK contains the canonical body PLUS the
    # SDK addendum. The body must be unchanged so the comparison is
    # fair; the addendum must be present so the model knows the names.
    assert SYSTEM_PROMPT in reviewer.SYSTEM_PROMPT_AGENT_SDK, (
        "shared SYSTEM_PROMPT must be embedded verbatim in SYSTEM_PROMPT_AGENT_SDK"
    )
    assert "<sdk_note>" in reviewer.SYSTEM_PROMPT_AGENT_SDK, (
        "SYSTEM_PROMPT_AGENT_SDK must include the <sdk_note> addendum"
    )
    assert "mcp__reviewer__submit_findings" in reviewer.SYSTEM_PROMPT_AGENT_SDK, (
        "addendum must reference the MCP-prefixed submit_findings name"
    )
    print(
        f"  [ok] SYSTEM_PROMPT_AGENT_SDK = SYSTEM_PROMPT (verbatim) + <sdk_note> "
        f"({len(reviewer.SYSTEM_PROMPT_AGENT_SDK):,} chars)"
    )

    # 3. MAX_TURNS parity with Client SDK. Hard-code the expected value
    # rather than reaching into the other module so a drift is caught.
    assert reviewer.MAX_TURNS == 100, (
        f"MAX_TURNS should be 100 for parity, got {reviewer.MAX_TURNS}"
    )
    print(f"  [ok] MAX_TURNS = {reviewer.MAX_TURNS} (parity with Client SDK)")

    # 4. SUBMIT_FINDINGS_TOOL_NAME is what we register.
    assert SUBMIT_FINDINGS_TOOL_NAME == "submit_findings", (
        "shared/findings expected canonical tool name"
    )
    print(f"  [ok] submit_findings registered under canonical name")

    # 5. _TraceWriter handles a minimal synthetic stream without raising.
    captured: list[str] = []
    writer = reviewer._TraceWriter(captured.append)

    # Synthetic "ResultMessage-like" duck — the writer reads .stop_reason,
    # .num_turns, .duration_ms, .total_cost_usd, .usage. Build a small
    # stand-in so we don't have to run the real harness.
    class _FakeResult:
        stop_reason = "end_turn"
        num_turns = 1
        duration_ms = 0
        total_cost_usd = 0.0
        usage = {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }

    # isinstance check inside _TraceWriter compares against ResultMessage
    # so a plain duck won't match — call the public write() with the real
    # type by importing it locally.
    from claude_agent_sdk import ResultMessage  # noqa: E402

    real_result = ResultMessage(
        subtype="result",
        duration_ms=0,
        duration_api_ms=0,
        is_error=False,
        num_turns=1,
        session_id="smoke",
        stop_reason="end_turn",
        total_cost_usd=0.0,
        usage=_FakeResult.usage,
        result=None,
        structured_output=None,
    )
    writer.write(real_result)
    writer.flush()
    assert any("RESULT" in line for line in captured), (
        "trace writer should produce a RESULT box for ResultMessage"
    )
    print("  [ok] _TraceWriter produces a RESULT box on ResultMessage")

    print("Test A: PASSED (5 assertions)")
    print()


# ---------------------------------------------------------------------------
# Test B — model in the loop (one API call, real Agent SDK)
# ---------------------------------------------------------------------------


def test_b_loop_with_tool_use() -> None:
    """Real run on the synthetic contract_mismatch fixture.

    This is the parity counterpart of smoke_phase16.test_b. We don't
    coerce specific tool calls (the Agent SDK doesn't have tool_choice
    forcing); we just assert that:

      - reviewer.run() returns the expected dict shape
      - submit_findings was called (submitted=True)
      - findings list is non-empty (the planted bug is obvious enough
        that the model should not return empty)
      - cost_usd > 0 and num_turns >= 1
      - trace and result files exist on disk

    On contract_mismatch this typically takes 1-3 turns at ~\$0.10-0.30.
    """
    print("=== Test B: model-driven loop (one API call, ~\$0.10-0.30) ===")
    with materialize(CONTRACT_MISMATCH) as fx:
        result = reviewer.run(fx.repo_path, fx.base_ref, fx.head_ref)

    print(
        f"  turns={result['num_turns']}  "
        f"cost=${result['cost_usd']:.4f}  "
        f"findings={len(result['findings'])}  "
        f"submitted={result['submitted']}  "
        f"exit={result['exit_reason']}"
    )

    # Parity-shape assertions — the suite runner relies on these keys.
    expected_keys = {
        "findings",
        "submitted",
        "duplicate_submission",
        "exit_reason",
        "cost_usd",
        "api_rate_cost_usd",
        "num_turns",
        "total_usage",
        "trace_path",
        "result_path",
        "run_id",
    }
    missing = expected_keys - set(result.keys())
    assert not missing, f"return dict missing parity keys: {sorted(missing)}"
    print(f"  [ok] return dict has all parity keys")

    # Behavioral assertions — fail loudly if the loop is broken.
    assert result["submitted"], (
        f"agent didn't submit findings; exit_reason={result['exit_reason']!r}"
    )
    assert isinstance(result["findings"], list), "findings must be a list"
    assert all(isinstance(f, Finding) for f in result["findings"]), (
        "findings must be parsed into Finding dataclasses"
    )
    assert len(result["findings"]) >= 1, (
        "agent returned empty findings on contract_mismatch — that's a regression"
    )
    assert result["cost_usd"] > 0, "cost_usd should be > 0 after a real API call"
    assert result["num_turns"] >= 1, "num_turns should be >= 1"
    print("  [ok] submitted=True, >=1 finding, cost>0, turns>=1")

    # Files exist on disk.
    assert Path(result["trace_path"]).is_file(), (
        f"trace file not written: {result['trace_path']}"
    )
    assert Path(result["result_path"]).is_file(), (
        f"result file not written: {result['result_path']}"
    )
    print(f"  [ok] trace + result files written ({result['trace_path']})")

    print("Test B: PASSED — loop ran, submitted findings, parity shape preserved")
    print()


if __name__ == "__main__":
    test_a_structure()
    test_b_loop_with_tool_use()
    print("All Phase 2.1 smoke tests passed.")
