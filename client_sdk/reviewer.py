"""Client SDK reviewer (Phase 1.5 — v0, single-shot).

Calls `shared.odis.build_context()` to assemble the curated review
context, then asks the model to surface bugs by forcing a single
`submit_findings` tool call. No agentic loop yet — that lands in Phase
1.6 with Read/Grep tools.

I/O contract is the one in docs/architecture.md ("Both reviewers
expose the identical run() signature"). The companion file is
`agent_sdk/reviewer.py`, landing in Phase 2.1.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

# Make the project root importable for `shared.*` and `pricing`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pricing  # noqa: E402
from shared.findings import (  # noqa: E402
    Finding,
    SUBMIT_FINDINGS_INPUT_SCHEMA,
    SUBMIT_FINDINGS_TOOL_DESCRIPTION,
    SUBMIT_FINDINGS_TOOL_NAME,
)
from shared.odis import build_context  # noqa: E402
from shared.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE  # noqa: E402

MODEL = "claude-opus-4-7"
MAX_TOKENS = 4096
# Safety cap. v0 typically uses 2 turns: (1) submit_findings call,
# (2) post-tool-result acknowledgement.
MAX_TURNS = 5

RESULTS_DIR = Path(__file__).parent / "results"
TRACES_DIR = Path(__file__).parent / "traces"

SUBMIT_FINDINGS_TOOL: dict[str, Any] = {
    "name": SUBMIT_FINDINGS_TOOL_NAME,
    "description": SUBMIT_FINDINGS_TOOL_DESCRIPTION,
    "input_schema": SUBMIT_FINDINGS_INPUT_SCHEMA,
}


def _next_run_id() -> int:
    TRACES_DIR.mkdir(exist_ok=True)
    used = [
        int(m.group(1))
        for p in TRACES_DIR.glob("run_*.txt")
        if (m := re.match(r"run_(\d+)\.txt$", p.name))
    ]
    return (max(used) + 1) if used else 1


def _write_trace(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _write_result(path: Path, run_id: int, repo: Path, refs: tuple[str, str],
                  findings: list[Finding], num_turns: int, usage: dict[str, int],
                  cost_usd: float) -> None:
    path.parent.mkdir(exist_ok=True)
    from dataclasses import asdict
    from json import dumps
    body = (
        f"# Client SDK reviewer run {run_id:03d}\n"
        f"# repo: {repo}\n"
        f"# refs: {refs[0]}..{refs[1]}\n"
        f"# turns: {num_turns}\n"
        f"# cost (USD, API rate): {cost_usd:.6f}\n"
        f"# usage: {usage}\n"
        f"# findings: {len(findings)}\n"
        f"# ---\n"
        f"{dumps([asdict(f) for f in findings], indent=2)}\n"
    )
    path.write_text(body)


def run(
    repo_path: Path,
    base_ref: str,
    head_ref: str,
    *,
    run_id: int | None = None,
    use_oauth: bool = False,  # ignored on Client SDK; kept for I/O symmetry
) -> dict[str, Any]:
    load_dotenv(override=True)
    if run_id is None:
        run_id = _next_run_id()
    trace_path = TRACES_DIR / f"run_{run_id:03d}.txt"
    result_path = RESULTS_DIR / f"run_{run_id:03d}.txt"

    context = build_context(repo_path, base_ref, head_ref)
    user_prompt = USER_PROMPT_TEMPLATE.format(odis_context=context)

    trace: list[str] = [
        f"=== Client SDK reviewer run {run_id:03d} ===",
        f"repo: {repo_path}",
        f"refs: {base_ref}..{head_ref}",
        f"started: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"--- system prompt ({len(SYSTEM_PROMPT)} chars) ---",
        SYSTEM_PROMPT,
        f"--- user prompt ({len(user_prompt)} chars) ---",
        user_prompt[:2000] + ("\n…(truncated for trace)" if len(user_prompt) > 2000 else ""),
        "",
    ]

    client = anthropic.Anthropic()
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_prompt},
    ]

    findings: list[Finding] = []
    total_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    num_turns = 0

    # `tool_choice` is forced on the FIRST call so the model definitely
    # produces structured output. After it does, we drop back to "auto"
    # (default) so the model can cleanly end the conversation rather
    # than calling submit_findings again.
    while num_turns < MAX_TURNS:
        is_first = num_turns == 0
        kwargs: dict[str, Any] = dict(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[SUBMIT_FINDINGS_TOOL],
            messages=messages,
        )
        if is_first:
            kwargs["tool_choice"] = {
                "type": "tool",
                "name": SUBMIT_FINDINGS_TOOL_NAME,
            }
        response = client.messages.create(**kwargs)
        num_turns += 1
        for k in total_usage:
            total_usage[k] += getattr(response.usage, k, 0) or 0
        trace.append(
            f"--- turn {num_turns} stop={response.stop_reason} "
            f"in={response.usage.input_tokens} out={response.usage.output_tokens} ---"
        )

        if response.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": response.content})
        results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "tool_use" and block.name == SUBMIT_FINDINGS_TOOL_NAME:
                raw = block.input.get("findings", [])
                findings = [Finding(**item) for item in raw]
                trace.append(f"submit_findings called with {len(findings)} finding(s)")
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "ok",
                })
        messages.append({"role": "user", "content": results})

    cost_usd = pricing.cost_usd(total_usage)
    trace.append("")
    trace.append(
        f"finished: {datetime.now(timezone.utc).isoformat()}  "
        f"turns={num_turns}  findings={len(findings)}  cost=${cost_usd:.4f}"
    )

    _write_trace(trace_path, trace)
    _write_result(result_path, run_id, repo_path, (base_ref, head_ref),
                  findings, num_turns, total_usage, cost_usd)

    return {
        "findings": findings,
        "cost_usd": cost_usd,
        "api_rate_cost_usd": cost_usd,  # Client SDK = same; no Max OAuth path
        "num_turns": num_turns,
        "total_usage": total_usage,
        "trace_path": str(trace_path),
        "result_path": str(result_path),
        "run_id": run_id,
    }
