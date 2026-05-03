"""Client SDK reviewer (Phase 1.6 v2 — "agent with a computer").

The agent gets a thin user prompt (repo path + refs) and a tools list
with bash / read_file_section / ast_search / grep / write_file /
build_review_context / submit_findings. ODIS is offered AS A TOOL,
not pre-baked into the user message — the model decides when to fetch
it. No tool_choice forcing.

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

# sys.path is bumped above; Repo lives in the project's sandbox/ module.
from sandbox.repo import Repo  # noqa: E402

# Make the project root importable for `shared.*` and `pricing`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pricing  # noqa: E402
from shared.agent_tools import (  # noqa: E402
    INVESTIGATION_TOOLS,
    ast_search,
    bash,
    build_review_context,
    grep,
    read_file_section,
    write_file,
)
from shared.findings import (  # noqa: E402
    Finding,
    SUBMIT_FINDINGS_INPUT_SCHEMA,
    SUBMIT_FINDINGS_TOOL_DESCRIPTION,
    SUBMIT_FINDINGS_TOOL_NAME,
)
from shared.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE  # noqa: E402

MODEL = "claude-opus-4-7"
# MAX_TOKENS bumped 4096 → 16000 in Phase 2.2 for effort="xhigh".
# The Anthropic Opus-4.7 docs suggest "starting at 64k" for xhigh, but
# the bare client errors out at >~19k without streaming (10-min
# heuristic timeout). We don't stream, and our largest observed
# per-turn output across the Phase 1.8 sweep was ~575 tokens average,
# so 16k gives ~25x headroom and still fits the non-streaming rule.
MAX_TOKENS = 16000
# Safety cap. With investigation tools available the agent may take
# several turns; we still want a hard ceiling. Caching keeps each
# additional turn cheap (the prefix is mostly cache_read), so the
# cap was raised in steps: 12 → 20 (Phase 1.7) → 100 (Phase 1.8 after
# sentry_93824 ran into the 20-cap mid-investigation on the
# multi-file flusher case).
MAX_TURNS = 100
# Phase 2.2 — pin reasoning effort. Anthropic recommends "xhigh" for
# coding/agentic tasks on Opus 4.7. Both reviewers (Client + Agent SDK)
# share this constant so the comparison is at the same effort level
# rather than each SDK's implicit default.
EFFORT = "xhigh"

RESULTS_DIR = Path(__file__).parent / "results"
TRACES_DIR = Path(__file__).parent / "traces"

# --------------------------------------------------------------------------- #
# Phase 1.7 — prompt caching
#
# Three breakpoints (well under Anthropic's 4-mark limit):
#   1. System prompt — large + perfectly stable across all turns. Biggest
#      single win.
#   2. Tools array — also stable. cache_control on the LAST tool causes the
#      whole array up to and including it to be cached.
#   3. Rolling last-message breakpoint — added inside the loop to the last
#      content block of the last user message. Each new turn hits the cache
#      for everything before this rotating mark, so the conversation prefix
#      grows but stays on the cheap side of the API rate card.
#
# Tool_results are NOT marked individually — the last-message rolling mark
# already covers them as part of the prefix, and adding a per-block mark
# could hit the +25% cost penalty we measured in compare.py run_008 of the
# offload script (cache write with 0 reads).
# --------------------------------------------------------------------------- #

CACHE_CONTROL_EPHEMERAL: dict[str, Any] = {"type": "ephemeral"}

SUBMIT_FINDINGS_TOOL: dict[str, Any] = {
    "name": SUBMIT_FINDINGS_TOOL_NAME,
    "description": SUBMIT_FINDINGS_TOOL_DESCRIPTION,
    "input_schema": SUBMIT_FINDINGS_INPUT_SCHEMA,
}

SEARCH_LEARNINGS_TOOL: dict[str, Any] = {
    "name": "search_learnings",
    "description": (
        "Search past maintainer corrections by free-text query. Use when "
        "the auto-injected <past_learnings> didn't surface something you "
        "suspect was previously taught. Returns top-5."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Code snippet OR natural-language description.",
            },
            "k": {"type": "integer", "default": 5, "maximum": 10},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

# All tools the agent has access to: investigation tools (decide what to
# look at) + submit_findings (terminate with structured output).
# `cache_control` on the LAST tool caches the entire tools array.
ALL_TOOLS: list[dict[str, Any]] = [
    *INVESTIGATION_TOOLS,
    SEARCH_LEARNINGS_TOOL,
    {**SUBMIT_FINDINGS_TOOL, "cache_control": CACHE_CONTROL_EPHEMERAL},
]


SYSTEM_BLOCKS: list[dict[str, Any]] = [
    {
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": CACHE_CONTROL_EPHEMERAL,
    }
]


def _stamp_last_message_for_cache(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a copy of `messages` with `cache_control` on the last
    content block of the last message, so the entire prefix up to that
    point becomes cacheable for the *next* turn's request.

    Anthropic's API allows up to 4 cache breakpoints per request. We
    use 3: system block, last tool, last message — well under the cap.
    Each turn the marker rotates forward as messages list grows.
    """
    if not messages:
        return messages
    out = [m for m in messages[:-1]]
    last = dict(messages[-1])
    content = last["content"]

    # Coerce string content into a single text block we can mark.
    if isinstance(content, str):
        last["content"] = [
            {
                "type": "text",
                "text": content,
                "cache_control": CACHE_CONTROL_EPHEMERAL,
            }
        ]
        out.append(last)
        return out

    # content is a list — could be dicts (we authored) or SDK objects
    # (came from response.content). Coerce each to a dict and mark the
    # final one.
    new_content: list[dict[str, Any]] = []
    last_idx = len(content) - 1
    for i, block in enumerate(content):
        if isinstance(block, dict):
            block_dict = dict(block)
        else:  # SDK content-block object
            block_dict = block.model_dump()
        if i == last_idx:
            block_dict["cache_control"] = CACHE_CONTROL_EPHEMERAL
        new_content.append(block_dict)
    last["content"] = new_content
    out.append(last)
    return out


def _dispatch_tool(repo: Repo, name: str, args: dict[str, Any]) -> str:
    """Run an investigation tool and return its result as a string.

    submit_findings is handled inline in the loop (it's the terminator)
    so this dispatcher only handles the read-only / scratch tools.
    Wraps every call in try/except so a malformed tool_use payload
    (missing required key, wrong type, etc.) cannot crash the loop —
    the model just sees an Error string and adapts.

    Phase 4: `repo` is now a `sandbox.repo.Repo` (LocalRepo or
    DaytonaRepo). The tool wrappers route everything through
    `repo.exec` / `repo.upload_bytes`.
    """
    try:
        if name == "build_review_context":
            return build_review_context(repo, args["base_ref"], args["head_ref"])
        if name == "bash":
            return bash(repo, args["command"])
        if name == "read_file_section":
            return read_file_section(
                repo, args["path"], args["start_line"], args["end_line"]
            )
        if name == "ast_search":
            return ast_search(repo, args["pattern"], args.get("language", "python"))
        if name == "grep":
            return grep(repo, args["pattern"], args.get("path_glob", ""))
        if name == "write_file":
            return write_file(repo, args["path"], args["content"])
        if name == "search_learnings":
            try:
                from learnings.config import load as load_cfg
                from learnings.qdrant_store import QdrantStore
                from learnings.voyage_client import VoyageClient
                from shared.learnings import search_tool_handler
                from shared.learnings_prompt import infer_repo_slug

                cfg = load_cfg()
                slug = infer_repo_slug(repo)
                if not slug:
                    return "<results/>"
                return search_tool_handler(
                    query=str(args.get("query", "")),
                    repo=slug,
                    store=QdrantStore(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key),
                    embedder=VoyageClient(api_key=cfg.voyage_api_key),
                    k=int(args.get("k", 5)),
                )
            except Exception as e:
                return f"<results error={str(e)!r}/>"
        return f"Error: unknown tool {name!r}"
    except (KeyError, TypeError, ValueError) as e:
        return f"Error: invalid args for {name}: {e}"


def _short_args(d: dict[str, Any], limit: int = 100) -> str:
    """Compact JSON-ish repr for trace lines."""
    import json
    s = json.dumps(d, default=str)
    return s if len(s) <= limit else s[: limit - 1] + "…"


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


def _write_result(path: Path, run_id: int, repo_label: str, refs: tuple[str, str],
                  findings: list[Finding], num_turns: int, usage: dict[str, int],
                  cost_usd: float) -> None:
    path.parent.mkdir(exist_ok=True)
    from dataclasses import asdict
    from json import dumps
    body = (
        f"# Client SDK reviewer run {run_id:03d}\n"
        f"# repo: {repo_label}\n"
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
    repo: Repo,
    base_ref: str,
    head_ref: str,
    *,
    run_id: int | None = None,
    use_oauth: bool = False,  # ignored on Client SDK; kept for I/O symmetry
) -> dict[str, Any]:
    """Drive one code review against `repo`.

    Phase 4: `repo` is a `sandbox.repo.Repo` (LocalRepo for the host
    backend, DaytonaRepo for the sandbox backend). The reviewer never
    touches the filesystem directly — every tool call goes through
    `_dispatch_tool(repo, ...)` which routes to `shared/agent_tools.py`
    wrappers, which in turn call `repo.exec` / `repo.upload_bytes`.
    """
    load_dotenv(override=True)
    if run_id is None:
        run_id = _next_run_id()
    trace_path = TRACES_DIR / f"run_{run_id:03d}.txt"
    result_path = RESULTS_DIR / f"run_{run_id:03d}.txt"

    # Phase 1.6 v2: ODIS is a TOOL the agent can call, not pre-baked
    # into the prompt. The user prompt is a thin directive pointing at
    # the repo + refs. The `repo_path` template field is a logical name
    # the model uses for context; the actual filesystem is opaque
    # behind the Repo abstraction.
    from shared.learnings_prompt import (
        build_user_prompt_with_learnings,
        infer_repo_slug,
    )
    repo_slug = infer_repo_slug(repo)
    user_prompt = build_user_prompt_with_learnings(repo, base_ref, head_ref, repo_slug)

    trace: list[str] = [
        f"=== Client SDK reviewer run {run_id:03d} ===",
        f"repo: {type(repo).__name__}",
        f"refs: {base_ref}..{head_ref}",
        f"started: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"--- system prompt ({len(SYSTEM_PROMPT)} chars) ---",
        SYSTEM_PROMPT,
        f"--- user prompt ({len(user_prompt)} chars) ---",
        user_prompt,
        "",
    ]

    client = anthropic.Anthropic()
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_prompt},
    ]

    findings: list[Finding] = []
    submitted: bool = False        # True once submit_findings has been called
    duplicate_submission: bool = False
    total_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    num_turns = 0
    exit_reason: str = "unknown"

    # No tool_choice — the model decides which tools to call. It can use
    # the investigation tools (read_file_section / ast_search / grep) to
    # dig deeper, then call submit_findings when it has a verdict.
    while num_turns < MAX_TURNS:
        cached_messages = _stamp_last_message_for_cache(messages)
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_BLOCKS,
            tools=ALL_TOOLS,
            messages=cached_messages,
            output_config={"effort": EFFORT},
        )
        num_turns += 1
        for k in total_usage:
            total_usage[k] += getattr(response.usage, k, 0) or 0
        trace.append(
            f"--- turn {num_turns} stop={response.stop_reason} "
            f"in={response.usage.input_tokens} out={response.usage.output_tokens} ---"
        )
        for block in response.content:
            if block.type == "text" and block.text.strip():
                trace.append(f"  [text] {block.text.strip()[:200]}")
            elif block.type == "tool_use":
                trace.append(f"  [tool_use] {block.name}({_short_args(block.input)})")

        if response.stop_reason != "tool_use":
            exit_reason = "stop_reason_" + str(response.stop_reason)
            break

        messages.append({"role": "assistant", "content": response.content})
        results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == SUBMIT_FINDINGS_TOOL_NAME:
                if submitted:
                    duplicate_submission = True
                    trace.append("  submit_findings called twice — keeping first")
                    tool_result_content = "ok"
                else:
                    # A malformed payload (wrong types, missing required keys,
                    # non-list `findings`) must not crash the loop — the model
                    # should see an Error string and adapt, exactly like for
                    # the investigation tools.
                    try:
                        raw = block.input.get("findings", []) if isinstance(block.input, dict) else []
                        parsed = [Finding(**item) for item in raw]
                    except (TypeError, ValueError, AttributeError) as e:
                        trace.append(f"  submit_findings rejected: {e}")
                        tool_result_content = (
                            f"Error: invalid submit_findings payload: {e}. "
                            "Re-call with the documented schema."
                        )
                    else:
                        findings = parsed
                        submitted = True
                        trace.append(f"  submit_findings → {len(findings)} finding(s)")
                        tool_result_content = "ok"
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_result_content,
                })
            else:
                tool_output = _dispatch_tool(repo, block.name, block.input)
                trace.append(f"  {block.name} → {len(tool_output)} chars")
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_output,
                })
        messages.append({"role": "user", "content": results})
    else:
        # Loop exited because num_turns >= MAX_TURNS without `break`.
        exit_reason = "max_turns"

    cost_usd = pricing.cost_usd(total_usage)
    trace.append("")
    trace.append(
        f"finished: {datetime.now(timezone.utc).isoformat()}  "
        f"turns={num_turns}  submitted={submitted}  "
        f"findings={len(findings)}  exit_reason={exit_reason}  "
        f"cost=${cost_usd:.4f}"
    )

    _write_trace(trace_path, trace)
    _write_result(
        result_path,
        run_id,
        type(repo).__name__,
        (base_ref, head_ref),
        findings,
        num_turns,
        total_usage,
        cost_usd,
    )

    return {
        "findings": findings,
        "submitted": submitted,
        "duplicate_submission": duplicate_submission,
        "exit_reason": exit_reason,
        "cost_usd": cost_usd,
        "api_rate_cost_usd": cost_usd,  # Client SDK = same; no Max OAuth path
        "num_turns": num_turns,
        "total_usage": total_usage,
        "trace_path": str(trace_path),
        "result_path": str(result_path),
        "run_id": run_id,
    }
