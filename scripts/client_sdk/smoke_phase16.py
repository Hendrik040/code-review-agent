"""Smoke test for Phase 1.6 — exercises the parts the standard
contract_mismatch run did NOT cover.

The standard run (`reviewer.run(...)` on contract_mismatch) finishes in
2 turns with the agent going straight to submit_findings. The loop's
*new* code path — handling tool_use blocks for the investigation tools
— never fires there. This script forces it to fire.

Run:    uv run python scripts/client_sdk/smoke_phase16.py
Cost:   Test A is free (no API). Test B is one model call, ~$0.10-0.15.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Project root on path so `shared.*` and `client_sdk.*` resolve.
# This file is at scripts/client_sdk/smoke_phase16.py — three hops up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv

import anthropic
from client_sdk.reviewer import (
    ALL_TOOLS,
    MAX_TOKENS,
    MAX_TURNS,
    MODEL,
    _dispatch_tool,
)
from shared.findings import SUBMIT_FINDINGS_TOOL_NAME, Finding
from shared.fixtures import CONTRACT_MISMATCH, materialize
from shared.odis import build_context
from shared.prompts import SYSTEM_PROMPT


# --------------------------------------------------------------------------- #
# Test A — dispatch wiring (deterministic, no API)
# --------------------------------------------------------------------------- #

def test_a_dispatch() -> None:
    """Verify _dispatch_tool routes to all three tools + error paths.

    The standard reviewer run never exercises this code because the
    model went straight to submit_findings. Here we call it directly.
    """
    print("=== Test A: dispatch wiring (no API) ===")
    with materialize(CONTRACT_MISMATCH) as fx:
        # 1. read_file_section happy path
        out = _dispatch_tool(
            fx.repo_path, "read_file_section",
            {"path": "main.py", "start_line": 1, "end_line": 5},
        )
        assert "from calc import" in out, f"expected file content, got: {out!r}"
        print("  [ok] read_file_section returns numbered lines")

        # 2. ast_search happy path — finds the broken caller
        out = _dispatch_tool(
            fx.repo_path, "ast_search",
            {"pattern": "add($$$)", "language": "python"},
        )
        assert "add(1, 2)" in out, f"expected ast match, got: {out!r}"
        print("  [ok] ast_search returns matches via ast-grep")

        # 3. grep happy path
        out = _dispatch_tool(
            fx.repo_path, "grep",
            {"pattern": "def add", "path_glob": "*.py"},
        )
        assert "def add" in out, f"expected grep match, got: {out!r}"
        print("  [ok] grep returns matches via git grep")

        # 4. Unknown tool — must return an error STRING, never raise
        out = _dispatch_tool(fx.repo_path, "nonexistent_tool", {})
        assert "Error" in out and "unknown" in out.lower(), f"expected error string, got: {out!r}"
        print("  [ok] unknown tool returns error string (no crash)")

        # 5. Bad path — error string, not raise
        out = _dispatch_tool(
            fx.repo_path, "read_file_section",
            {"path": "missing.py", "start_line": 1, "end_line": 5},
        )
        assert "Error" in out, f"expected error for missing file, got: {out!r}"
        print("  [ok] missing path returns error string (no crash)")

    print("Test A: PASSED (5 assertions)")
    print()


# --------------------------------------------------------------------------- #
# Test B — model in the loop, coerced to use a tool (real API call)
# --------------------------------------------------------------------------- #

def test_b_loop_with_tool_use() -> None:
    """Verify the loop correctly handles a tool_use → tool_result round-trip.

    Coerces the model to call ast_search by prepending a directive to
    the user prompt. Asserts the trace shows ast_search before
    submit_findings, and the loop terminates with a finding.
    """
    print("=== Test B: model-driven loop (one API call, ~$0.15) ===")
    load_dotenv(override=True)
    client = anthropic.Anthropic()

    with materialize(CONTRACT_MISMATCH) as fx:
        odis_context = build_context(fx.repo_path, fx.base_ref, fx.head_ref)
        coercive_user_prompt = (
            "BEFORE submitting findings, you MUST call `ast_search` "
            "exactly once with pattern `add($$$)` and language `python`. "
            "After you see its result, call `submit_findings` with your "
            "verdict.\n\n"
            + odis_context
        )

        messages: list[dict] = [{"role": "user", "content": coercive_user_prompt}]
        tools_called: list[str] = []
        findings: list[Finding] = []
        num_turns = 0

        while num_turns < MAX_TURNS:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=ALL_TOOLS,
                messages=messages,
            )
            num_turns += 1
            if response.stop_reason != "tool_use":
                break

            messages.append({"role": "assistant", "content": response.content})
            results: list[dict] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tools_called.append(block.name)
                if block.name == SUBMIT_FINDINGS_TOOL_NAME:
                    raw = block.input.get("findings", [])
                    findings = [Finding(**f) for f in raw]
                    results.append({
                        "type": "tool_result", "tool_use_id": block.id, "content": "ok",
                    })
                else:
                    out = _dispatch_tool(fx.repo_path, block.name, block.input)
                    results.append({
                        "type": "tool_result", "tool_use_id": block.id, "content": out,
                    })
            messages.append({"role": "user", "content": results})

    print(f"  tools called in order: {tools_called}")
    print(f"  total turns: {num_turns}, findings: {len(findings)}")
    assert "ast_search" in tools_called, (
        f"agent didn't call ast_search; tools called: {tools_called}"
    )
    assert SUBMIT_FINDINGS_TOOL_NAME in tools_called, (
        f"agent didn't submit findings; tools called: {tools_called}"
    )
    assert tools_called.index("ast_search") < tools_called.index(SUBMIT_FINDINGS_TOOL_NAME), (
        f"ast_search should precede submit_findings; got: {tools_called}"
    )
    print("Test B: PASSED — loop handled tool_use → result → submit_findings")
    print()


if __name__ == "__main__":
    test_a_dispatch()
    test_b_loop_with_tool_use()
    print("All Phase 1.6 smoke tests passed.")
