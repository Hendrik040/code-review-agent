"""Agent SDK reviewer (Phase 2.1) — parity with client_sdk/reviewer.py.

Same `run(repo_path, base_ref, head_ref) -> dict` contract as the Client
SDK so `compare.py --task review` (Phase 3.1) can drive both side by
side.

What's different here is HARNESS-LEVEL — the literal point of the
comparison:

  - Investigation tools come from the Agent SDK harness: `Read`,
    `Bash`, `Grep`, `Glob`. They are PascalCase (the canonical
    Agent-SDK names) and the harness provides built-in offloading on
    large outputs — we don't reimplement them.

  - Our two project-specific tools (`build_review_context` for the
    ODIS slice, `submit_findings` as the structured terminator) live
    in an in-process MCP server registered via
    `create_sdk_mcp_server`. They are visible to the model as
    `mcp__reviewer__build_review_context` and
    `mcp__reviewer__submit_findings`.

  - Caching is harness-managed; we do NOT add `cache_control`
    breakpoints (Client SDK does this manually because it has the
    bare API). Whatever caching the harness does is part of what we
    are comparing.

  - Cost / num_turns / usage come straight from the final
    `ResultMessage`. We do not maintain our own counters.

The shared `SYSTEM_PROMPT` from `shared/prompts.py` references the
Client SDK tool names (`bash`, `read_file_section`, ...). We append a
small `<sdk_note>` paragraph mapping those references to the
harness-native names so the model is not confused. Body of the prompt
(workflow / finding contract / rules) is identical between SDKs — that
is what keeps the comparison fair.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Project root on path so `shared.*` and `pricing` resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pricing  # noqa: E402
from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    UserMessage,
    create_sdk_mcp_server,
    query,
    tool,
)
from dotenv import load_dotenv  # noqa: E402

from sandbox.repo import Repo  # noqa: E402
from shared.agent_tools import (  # noqa: E402
    AST_SEARCH_TOOL,
    BASH_TOOL,
    BUILD_REVIEW_CONTEXT_TOOL,
    GREP_TOOL,
    READ_FILE_SECTION_TOOL,
    WRITE_FILE_TOOL,
    ast_search as _ast_search_impl,
    bash as _bash_impl,
    build_review_context as _build_context_impl,
    grep as _grep_impl,
    read_file_section as _read_file_section_impl,
    write_file as _write_file_impl,
)
from shared.findings import (  # noqa: E402
    Finding,
    SUBMIT_FINDINGS_INPUT_SCHEMA,
    SUBMIT_FINDINGS_TOOL_DESCRIPTION,
    SUBMIT_FINDINGS_TOOL_NAME,
)
from shared.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE  # noqa: E402

MODEL = "claude-opus-4-7"
MAX_TURNS = 100  # parity with client_sdk/reviewer.py
# Per-call output budget — informational on the Agent SDK side.
# ClaudeAgentOptions does not expose a per-call max_tokens equivalent
# (the harness sizes it internally), but we pin the same number the
# Client SDK uses so any drift between SDKs is documented.
MAX_TOKENS = 16000
# Default to "max" — the most capable mode, matching the README's
# quick-start framing ("review a real PR with maximum effort"). For
# benchmarking + Client-vs-Agent comparisons (Phase 2.2 / 2.3 sweeps)
# pin this to "high" or "xhigh" so the two SDKs stay at the same
# reasoning depth. Other valid values: "low" | "medium" | "high" |
# "xhigh" | "max".
EFFORT = "max"

RESULTS_DIR = Path(__file__).parent / "results"
TRACES_DIR = Path(__file__).parent / "traces"


# ---------------------------------------------------------------------------
# Prompt addendum — Agent SDK tool names
#
# The shared SYSTEM_PROMPT lists the Client SDK tool names so the
# review *method* and *finding contract* are identical between SDKs.
# This addendum tells the model which concrete names to call on this
# implementation. Keep it short and stable.
# ---------------------------------------------------------------------------

SDK_ADDENDUM = """\
<sdk_note>
This implementation runs on the Claude Agent SDK harness, but the
agent operates exclusively against an isolated sandbox (Phase 4 —
Daytona or a host tempdir). Your investigation tools all proxy into
that sandbox via in-process MCP — the harness's native Read/Bash/
Grep are NOT available; everything you see is mcp__reviewer__*:

  - mcp__reviewer__bash                  (shell in the sandbox)
  - mcp__reviewer__read_file_section     (file/section read)
  - mcp__reviewer__grep                  (regex search via git grep)
  - mcp__reviewer__ast_search            (structural search via ast-grep)
  - mcp__reviewer__write_file            (write a file in the sandbox)
  - mcp__reviewer__build_review_context  (the ODIS curated slice;
                                          your recommended first call)
  - mcp__reviewer__submit_findings       (the terminator)

The names differ in prefix from <action_space>; the *purpose*
described there still applies. Tool surface is identical to the
Client SDK reviewer. Finish by calling
mcp__reviewer__submit_findings exactly once.
</sdk_note>
"""

SYSTEM_PROMPT_AGENT_SDK = SYSTEM_PROMPT + "\n" + SDK_ADDENDUM


# ---------------------------------------------------------------------------
# Trace writer — boxed turn-by-turn view of the SDK message stream.
# Copied from agent_sdk/offload_runner.py with light edits so the trace
# looks the same shape between Phase 0 (offload) and Phase 2 (reviewer).
# ---------------------------------------------------------------------------


def _wrap(s: str, width: int) -> list[str]:
    out: list[str] = []
    line = s
    while len(line) > width:
        out.append(line[:width])
        line = line[width:]
    out.append(line)
    return out


def _draw_box(log, header: str, lines: list[str]) -> None:
    pad = max(2, 78 - len(header) - 4)
    log(f"┌─ {header} {'─' * pad}┐")
    for line in lines:
        if not line:
            log("│")
            continue
        for chunk in _wrap(line, 76):
            log(f"│ {chunk}")
    log(f"└{'─' * (len(header) + pad + 3)}┘")
    log("")


def _short_args(d: Any, limit: int = 240) -> str:
    s = json.dumps(d, default=str)
    return (s[:limit] + "…") if len(s) > limit else s


def _block_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return "" if content is None else str(content)


class _TraceWriter:
    def __init__(self, log):
        self.log = log
        self.turn = 0
        self.tool_names: dict[str, str] = {}
        self._buf_kind: str | None = None
        self._buf_lines: list[str] = []
        self._buf_msg_id: str | None = None

    def flush(self) -> None:
        if self._buf_kind is None:
            return
        self.turn += 1
        header = f"TURN {self.turn:02d}  [{self._buf_kind}]"
        _draw_box(self.log, header, self._buf_lines)
        self._buf_kind = None
        self._buf_lines = []
        self._buf_msg_id = None

    def _append_assistant_blocks(self, msg: Any, first: bool) -> None:
        if first:
            u = getattr(msg, "usage", None) or {}
            if isinstance(u, dict):
                self._buf_lines.append(
                    f"usage: in={u.get('input_tokens', 0)} "
                    f"cache_w={u.get('cache_creation_input_tokens', 0)} "
                    f"cache_r={u.get('cache_read_input_tokens', 0)} "
                    f"out={u.get('output_tokens', 0)}"
                )
        for block in msg.content:
            btype = type(block).__name__
            if btype == "TextBlock":
                self._buf_lines.append("")
                self._buf_lines.append("text:")
                for tline in (block.text or "").splitlines() or [""]:
                    self._buf_lines.append(f"  {tline}")
            elif btype == "ToolUseBlock":
                self.tool_names[block.id] = block.name
                self._buf_lines.append("")
                self._buf_lines.append(f"tool_use: {block.name}")
                self._buf_lines.append(f"  args: {_short_args(block.input)}")
            elif btype == "ThinkingBlock":
                self._buf_lines.append("")
                self._buf_lines.append("thinking: (omitted)")

    def write(self, msg: Any) -> None:
        cls = type(msg).__name__
        if isinstance(msg, AssistantMessage):
            mid = getattr(msg, "message_id", None)
            if mid and mid == self._buf_msg_id and self._buf_kind == "assistant":
                self._append_assistant_blocks(msg, first=False)
            else:
                self.flush()
                self._buf_kind = "assistant"
                self._buf_msg_id = mid
                self._append_assistant_blocks(msg, first=True)
        elif isinstance(msg, UserMessage):
            self.flush()
            for block in msg.content:
                if not (hasattr(block, "tool_use_id") and hasattr(block, "content")):
                    continue
                name = self.tool_names.get(block.tool_use_id, "?")
                text = _block_text(block.content)
                err = "  (ERROR)" if getattr(block, "is_error", False) else ""
                self._buf_kind = "tool_result"
                self._buf_lines = [
                    f"for: {name}{err}",
                    f"id : {block.tool_use_id}",
                    f"chars: {len(text):,}",
                ]
                if text:
                    self._buf_lines.append("")
                    self._buf_lines.append("preview:")
                    preview = text[:600]
                    for pline in preview.splitlines()[:10]:
                        self._buf_lines.append(f"  {pline}")
                    if len(text) > 600:
                        self._buf_lines.append(
                            f"  … (+{len(text) - 600:,} more chars)"
                        )
                self.flush()
        elif isinstance(msg, ResultMessage):
            self.flush()
            u = msg.usage or {}
            self._buf_kind = "RESULT"
            self._buf_lines = [
                f"stop_reason: {msg.stop_reason}",
                f"num_turns: {msg.num_turns}",
                f"duration: {msg.duration_ms} ms",
                f"total_cost_usd: ${getattr(msg, 'total_cost_usd', 0) or 0:.4f}",
                f"totals: in={u.get('input_tokens', 0)} "
                f"cache_w={u.get('cache_creation_input_tokens', 0)} "
                f"cache_r={u.get('cache_read_input_tokens', 0)} "
                f"out={u.get('output_tokens', 0)}",
            ]
            self.flush()
        elif cls == "SystemMessage" and getattr(msg, "subtype", None) == "init":
            self.flush()
            d = getattr(msg, "data", {}) or {}
            self._buf_kind = "INIT"
            self._buf_lines = [
                f"model: {d.get('model')}",
                f"cwd  : {d.get('cwd')}",
            ]
            self.flush()


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def _next_run_id() -> int:
    TRACES_DIR.mkdir(exist_ok=True)
    used = [
        int(m.group(1))
        for p in TRACES_DIR.glob("run_*.txt")
        if (m := re.match(r"run_(\d+)\.txt$", p.name))
    ]
    return (max(used) + 1) if used else 1


def _wrap_text(text: str) -> dict[str, Any]:
    """Standard MCP success envelope around a tool wrapper's return text."""
    return {"content": [{"type": "text", "text": text}]}


async def _run_async(
    repo: Repo,
    base_ref: str,
    head_ref: str,
    *,
    run_id: int | None,
    use_oauth: bool,
) -> dict[str, Any]:
    if run_id is None:
        run_id = _next_run_id()
    trace_path = TRACES_DIR / f"run_{run_id:03d}.txt"
    result_path = RESULTS_DIR / f"run_{run_id:03d}.txt"

    # Closure-captured state for the in-process MCP tools.
    captured_findings: list[Finding] = []
    submitted = [False]
    duplicate_submission = [False]

    # ------------------------------------------------------------------ #
    # MCP tool proxies. Each one delegates to the corresponding wrapper
    # in shared/agent_tools.py — the wrappers route everything through
    # `repo.exec` / `repo.upload_bytes`, so behavior is identical to
    # the Client SDK path. Phase 4 added `bash`, `read_file_section`,
    # and `grep` proxies (replacing the harness's Read/Bash/Grep) so
    # ALL repo-touching IO happens inside the sandbox.
    # ------------------------------------------------------------------ #

    @tool(
        BUILD_REVIEW_CONTEXT_TOOL["name"],
        BUILD_REVIEW_CONTEXT_TOOL["description"],
        BUILD_REVIEW_CONTEXT_TOOL["input_schema"],
    )
    async def _build_review_context(args: dict[str, Any]) -> dict[str, Any]:
        return _wrap_text(_build_context_impl(repo, args["base_ref"], args["head_ref"]))

    @tool(
        BASH_TOOL["name"],
        BASH_TOOL["description"],
        BASH_TOOL["input_schema"],
    )
    async def _bash(args: dict[str, Any]) -> dict[str, Any]:
        return _wrap_text(_bash_impl(repo, args["command"]))

    @tool(
        READ_FILE_SECTION_TOOL["name"],
        READ_FILE_SECTION_TOOL["description"],
        READ_FILE_SECTION_TOOL["input_schema"],
    )
    async def _read_file_section(args: dict[str, Any]) -> dict[str, Any]:
        return _wrap_text(
            _read_file_section_impl(
                repo, args["path"], args["start_line"], args["end_line"]
            )
        )

    @tool(
        GREP_TOOL["name"],
        GREP_TOOL["description"],
        GREP_TOOL["input_schema"],
    )
    async def _grep(args: dict[str, Any]) -> dict[str, Any]:
        return _wrap_text(
            _grep_impl(repo, args["pattern"], args.get("path_glob", ""))
        )

    @tool(
        AST_SEARCH_TOOL["name"],
        AST_SEARCH_TOOL["description"],
        AST_SEARCH_TOOL["input_schema"],
    )
    async def _ast_search(args: dict[str, Any]) -> dict[str, Any]:
        return _wrap_text(
            _ast_search_impl(repo, args["pattern"], args.get("language", "python"))
        )

    @tool(
        WRITE_FILE_TOOL["name"],
        WRITE_FILE_TOOL["description"],
        WRITE_FILE_TOOL["input_schema"],
    )
    async def _write_file(args: dict[str, Any]) -> dict[str, Any]:
        return _wrap_text(_write_file_impl(repo, args["path"], args["content"]))

    @tool(
        "search_learnings",
        "Search past maintainer corrections by free-text query. Use when "
        "the auto-injected <past_learnings> didn't surface something you "
        "suspect was previously taught. Returns top-5. "
        "For tactics on phrasing the query, read `shared/skills/learnings_search.md` first.",
        {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Code snippet OR natural-language description.",
                },
                "k": {"type": "integer", "default": 5, "maximum": 10, "minimum": 1},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    )
    async def _search_learnings(args: dict[str, Any]) -> dict[str, Any]:
        try:
            from learnings.config import load as load_cfg
            from learnings.qdrant_store import QdrantStore
            from learnings.voyage_client import VoyageClient
            from shared.learnings import search_tool_handler
            from shared.learnings_prompt import infer_repo_slug

            cfg = load_cfg()
            slug = infer_repo_slug(repo)
            if not slug:
                return _wrap_text("<results/>")
            xml = search_tool_handler(
                query=str(args.get("query", "")),
                repo=slug,
                store=QdrantStore(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key),
                embedder=VoyageClient(api_key=cfg.voyage_api_key),
                k=int(args.get("k", 5)),
            )
            return _wrap_text(xml)
        except Exception as e:
            # Sanitize: only the exception class name leaks to the model
            # and trace files (Voyage/Qdrant errors can embed credentials
            # in URLs). Full repr goes to debug log only. Spec §8.2.
            logging.warning("agent_sdk search_learnings failed: %r", e)
            return _wrap_text(f"<results error={type(e).__name__!r}/>")

    @tool(
        SUBMIT_FINDINGS_TOOL_NAME,
        SUBMIT_FINDINGS_TOOL_DESCRIPTION,
        SUBMIT_FINDINGS_INPUT_SCHEMA,
    )
    async def _submit_findings(args: dict[str, Any]) -> dict[str, Any]:
        # First call wins; subsequent calls return ok but don't mutate
        # the captured list (matches Client SDK behavior).
        if submitted[0]:
            duplicate_submission[0] = True
            return _wrap_text(
                "ok (duplicate submission ignored — first one is recorded)"
            )
        # Defensive parsing (matches the Client SDK's try/except so a
        # malformed payload doesn't kill the run).
        try:
            raw = args.get("findings", []) if isinstance(args, dict) else []
            parsed = [Finding(**item) for item in raw]
        except (TypeError, ValueError, AttributeError) as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Error: invalid submit_findings payload: {e}. "
                            "Re-call with the documented schema."
                        ),
                    }
                ],
                "is_error": True,
            }
        captured_findings.extend(parsed)
        submitted[0] = True
        return _wrap_text("ok")

    server = create_sdk_mcp_server(
        name="reviewer",
        version="0.1.0",
        tools=[
            _build_review_context,
            _bash,
            _read_file_section,
            _grep,
            _ast_search,
            _write_file,
            _search_learnings,
            _submit_findings,
        ],
    )

    from shared.learnings_prompt import (
        build_user_prompt_with_learnings,
        infer_repo_slug,
    )
    repo_slug = infer_repo_slug(repo)
    user_prompt = build_user_prompt_with_learnings(repo, base_ref, head_ref, repo_slug)

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=SYSTEM_PROMPT_AGENT_SDK,
        mcp_servers={"reviewer": server},
        # Phase 4 — every tool the agent can call is now an MCP proxy
        # routed through `repo.exec` / `repo.upload_bytes`. Harness
        # `Read`/`Bash`/`Grep` are explicitly NOT allowed; if we
        # included them, they would run in the local Python process
        # and could touch the host filesystem, defeating the
        # isolation goal.
        #   bash                  → mcp__reviewer__bash
        #   read_file_section     → mcp__reviewer__read_file_section
        #   grep                  → mcp__reviewer__grep
        #   ast_search            → mcp__reviewer__ast_search
        #   write_file            → mcp__reviewer__write_file
        #   build_review_context  → mcp__reviewer__build_review_context
        #   search_learnings      → mcp__reviewer__search_learnings
        #   submit_findings       → mcp__reviewer__submit_findings
        allowed_tools=[
            "mcp__reviewer__bash",
            "mcp__reviewer__read_file_section",
            "mcp__reviewer__grep",
            "mcp__reviewer__ast_search",
            "mcp__reviewer__write_file",
            "mcp__reviewer__build_review_context",
            "mcp__reviewer__search_learnings",
            "mcp__reviewer__submit_findings",
        ],
        # CR caught the harness auto-injecting `ToolSearch` — a tool
        # we didn't allow but Claude was using anyway. That breaks
        # tool-surface parity with the Client SDK (which has no such
        # tool). Disallow explicitly so the comparison stays apples-
        # to-apples.
        disallowed_tools=["ToolSearch"],
        permission_mode="bypassPermissions",
        max_turns=MAX_TURNS,
        effort=EFFORT,
        # `cwd` is intentionally left unset. With harness Read/Bash/
        # Grep disallowed, there's nothing on the harness side that
        # would honor it — every IO lives behind our MCP proxies and
        # cwd resolution happens inside Repo.exec.
    )
    # NOTE on per-call max_tokens parity with Client SDK:
    # ClaudeAgentOptions does not expose an API-level `max_tokens`
    # equivalent — the harness sizes it internally based on effort
    # level. The Client SDK pins MAX_TOKENS=16000; the Agent SDK
    # relies on the harness's internal sizing. In practice the
    # Anthropic docs recommend "starting at 64k tokens" for xhigh,
    # and the harness almost certainly defaults to something at
    # least that large. This is a real asymmetry we cannot remove
    # at this layer; document it in PLAN.md rather than fight it.

    saved_api_key = os.environ.pop("ANTHROPIC_API_KEY", None) if use_oauth else None

    TRACES_DIR.mkdir(exist_ok=True)
    trace = trace_path.open("w")

    def log(s: str) -> None:
        trace.write(s + "\n")
        trace.flush()

    log(f"=== Agent SDK reviewer run {run_id:03d} ===")
    log(f"repo: {type(repo).__name__}")
    log(f"refs: {base_ref}..{head_ref}")
    log(f"started: {datetime.now(timezone.utc).isoformat()}")
    log(f"use_oauth: {use_oauth}")
    log("")
    log(f"--- system prompt ({len(SYSTEM_PROMPT_AGENT_SDK)} chars) ---")
    log(SYSTEM_PROMPT_AGENT_SDK)
    log(f"--- user prompt ({len(user_prompt)} chars) ---")
    log(user_prompt)
    log("")

    writer = _TraceWriter(log)
    cost_usd: float | None = None
    total_usage: dict[str, Any] | None = None
    num_turns: int = 0
    stop_reason: str | None = None

    try:
        async for msg in query(prompt=user_prompt, options=options):
            writer.write(msg)
            if isinstance(msg, ResultMessage):
                cost_usd = getattr(msg, "total_cost_usd", None)
                total_usage = dict(msg.usage) if msg.usage else None
                num_turns = msg.num_turns
                stop_reason = msg.stop_reason
    finally:
        writer.flush()
        if saved_api_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved_api_key
        log("")
        log(
            f"finished: {datetime.now(timezone.utc).isoformat()}  "
            f"submitted={submitted[0]}  "
            f"duplicate_submission={duplicate_submission[0]}  "
            f"findings={len(captured_findings)}  "
            f"num_turns={num_turns}  "
            f"stop_reason={stop_reason}"
        )
        trace.close()

    # exit_reason mirrors Client SDK semantics so the suite-runner can
    # use the same column header for both SDKs.
    if submitted[0]:
        exit_reason = "submit_findings"
    elif num_turns >= MAX_TURNS:
        exit_reason = "max_turns"
    elif stop_reason:
        exit_reason = f"stop_reason_{stop_reason}"
    else:
        exit_reason = "unknown"

    api_rate_cost = pricing.cost_usd(total_usage) if total_usage else 0.0
    actual_cost = cost_usd if cost_usd is not None else api_rate_cost

    RESULTS_DIR.mkdir(exist_ok=True)
    result_path.write_text(
        f"# Agent SDK reviewer run {run_id:03d}\n"
        f"# repo: {type(repo).__name__}\n"
        f"# refs: {base_ref}..{head_ref}\n"
        f"# turns: {num_turns}\n"
        f"# cost (USD, harness-reported): {actual_cost:.6f}\n"
        f"# cost (USD, public Opus 4 rate): {api_rate_cost:.6f}\n"
        f"# usage: {total_usage}\n"
        f"# findings: {len(captured_findings)}\n"
        f"# exit_reason: {exit_reason}\n"
        f"# ---\n"
        f"{json.dumps([asdict(f) for f in captured_findings], indent=2)}\n"
    )

    return {
        "findings": captured_findings,
        "submitted": submitted[0],
        "duplicate_submission": duplicate_submission[0],
        "exit_reason": exit_reason,
        "cost_usd": actual_cost,
        "api_rate_cost_usd": api_rate_cost,
        "num_turns": num_turns,
        "total_usage": total_usage,
        "trace_path": str(trace_path),
        "result_path": str(result_path),
        "run_id": run_id,
    }


def run(
    repo: Repo,
    base_ref: str,
    head_ref: str,
    *,
    run_id: int | None = None,
    use_oauth: bool = False,
) -> dict[str, Any]:
    """Synchronous wrapper matching `client_sdk.reviewer.run` signature.

    Phase 4: `repo` is a `sandbox.repo.Repo`. The suite runner and
    `compare.py` (Phase 3.1) both expect this sync entry point;
    internally we drive the async query() generator via asyncio.run().
    """
    load_dotenv(override=True)
    return asyncio.run(
        _run_async(
            repo=repo,
            base_ref=base_ref,
            head_ref=head_ref,
            run_id=run_id,
            use_oauth=use_oauth,
        )
    )
