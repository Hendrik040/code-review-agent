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

from shared.findings import (  # noqa: E402
    Finding,
    SUBMIT_FINDINGS_INPUT_SCHEMA,
    SUBMIT_FINDINGS_TOOL_DESCRIPTION,
    SUBMIT_FINDINGS_TOOL_NAME,
)
from shared.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE  # noqa: E402

MODEL = "claude-opus-4-7"
MAX_TURNS = 100  # parity with client_sdk/reviewer.py

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
This implementation runs on the Claude Agent SDK harness. Your
investigation tools have these exact names in this environment:
  - Read                                 (read a file or section)
  - Bash                                 (run a shell command in the repo)
  - Grep                                 (regex search across files)
  - Glob                                 (file-name pattern matching)
  - mcp__reviewer__build_review_context  (the ODIS curated slice;
                                          your recommended first call)
  - mcp__reviewer__submit_findings       (the terminator)

The names differ in casing/prefix from <action_space>; the *purpose*
described there still applies. The harness's `Read` tool is the
equivalent of `read_file_section`; `Bash` covers anything `bash`
covered; `Grep` plus `Glob` covers what `grep` plus `ast_search`
covered (use `Grep` for both regex and structural patterns — there is
no separate ast_search tool here). Finish by calling
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


async def _run_async(
    repo_path: Path,
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

    @tool(
        "build_review_context",
        (
            "Build a curated review context for a git diff: the unified "
            "diff plus one-hop callers and callees of the changed symbols "
            "(the ODIS algorithm). HIGHLY RECOMMENDED as your first action "
            "— cheap (~1-5 KB), surfaces most boundary bugs (signature "
            "changes with un-updated callers) immediately. Pass the refs "
            "from the user prompt."
        ),
        {"base_ref": str, "head_ref": str},
    )
    async def _build_review_context(args: dict[str, Any]) -> dict[str, Any]:
        # Local import keeps the module load cheap and avoids any
        # circular-import paranoia.
        from shared.odis import build_context

        try:
            text = build_context(repo_path, args["base_ref"], args["head_ref"])
            return {"content": [{"type": "text", "text": text}]}
        except Exception as e:  # noqa: BLE001 — boundary; surface to model
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Error: build_review_context failed "
                            f"({type(e).__name__}): {e}"
                        ),
                    }
                ],
                "is_error": True,
            }

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
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "ok (duplicate submission ignored — first one is recorded)",
                    }
                ]
            }
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
        return {"content": [{"type": "text", "text": "ok"}]}

    server = create_sdk_mcp_server(
        name="reviewer",
        version="0.1.0",
        tools=[_build_review_context, _submit_findings],
    )

    user_prompt = USER_PROMPT_TEMPLATE.format(
        repo_path=str(repo_path),
        base_ref=base_ref,
        head_ref=head_ref,
    )

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=SYSTEM_PROMPT_AGENT_SDK,
        mcp_servers={"reviewer": server},
        allowed_tools=[
            "mcp__reviewer__build_review_context",
            "mcp__reviewer__submit_findings",
            "Read",
            "Bash",
            "Grep",
            "Glob",
        ],
        permission_mode="bypassPermissions",
        max_turns=MAX_TURNS,
        cwd=str(repo_path),
    )

    saved_api_key = os.environ.pop("ANTHROPIC_API_KEY", None) if use_oauth else None

    TRACES_DIR.mkdir(exist_ok=True)
    trace = trace_path.open("w")

    def log(s: str) -> None:
        trace.write(s + "\n")
        trace.flush()

    log(f"=== Agent SDK reviewer run {run_id:03d} ===")
    log(f"repo: {repo_path}")
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
        f"# repo: {repo_path}\n"
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
    repo_path: Path,
    base_ref: str,
    head_ref: str,
    *,
    run_id: int | None = None,
    use_oauth: bool = False,
) -> dict[str, Any]:
    """Synchronous wrapper matching `client_sdk.reviewer.run` signature.

    The suite runner and `compare.py` (Phase 3.1) both expect a sync
    callable. Internally we drive the async query() generator via
    asyncio.run().
    """
    load_dotenv(override=True)
    return asyncio.run(
        _run_async(
            repo_path=Path(repo_path),
            base_ref=base_ref,
            head_ref=head_ref,
            run_id=run_id,
            use_oauth=use_oauth,
        )
    )
