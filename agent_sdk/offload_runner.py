"""Agent SDK path: fetch_url tool registered as an in-process MCP server,
driven through `claude_agent_sdk.query`. Returns what the model received as
tool_result, plus the next-turn input_tokens. Writes a streaming trace of
every message yielded by the SDK to `traces/run_NNN.txt`."""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pricing  # noqa: E402
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    UserMessage,
    create_sdk_mcp_server,
    query,
    tool,
)

MODEL = "claude-opus-4-7"
PROMPT = (
    "Use the fetch_url tool to fetch {url}. Then write a 2-3 sentence "
    "summary of what the page is about."
)
UA = "tool-offload-compare/0.1 httpx"
TRACES_DIR = Path(__file__).parent / "traces"
RESULTS_DIR = Path(__file__).parent / "results"


@tool("fetch_url", "Fetch a URL via HTTP GET and return the body as text.", {"url": str})
async def _fetch_url(args: dict[str, Any]) -> dict[str, Any]:
    body = httpx.get(
        args["url"], follow_redirects=True, timeout=30.0,
        headers={"User-Agent": UA},
    ).text
    return {"content": [{"type": "text", "text": body}]}


def _block_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return "" if content is None else str(content)


def _next_run_id() -> int:
    TRACES_DIR.mkdir(exist_ok=True)
    used = [int(m.group(1)) for p in TRACES_DIR.glob("run_*.txt")
            if (m := re.match(r"run_(\d+)\.txt$", p.name))]
    return (max(used) + 1) if used else 1


_RULE = "─" * 78


def _draw_box(log, header: str, lines: list[str]) -> None:
    pad = max(2, 78 - len(header) - 4)
    log(f"┌─ {header} {'─' * pad}┐")
    for line in lines:
        # wrap long lines so the trace stays scannable in a terminal
        if not line:
            log("│")
            continue
        for chunk in _wrap(line, 76):
            log(f"│ {chunk}")
    log(f"└{'─' * (len(header) + pad + 3)}┘")
    log("")


def _wrap(s: str, width: int) -> list[str]:
    out: list[str] = []
    line = s
    while len(line) > width:
        out.append(line[:width])
        line = line[width:]
    out.append(line)
    return out


def _short_args(d: Any, limit: int = 240) -> str:
    s = json.dumps(d, default=str)
    return (s[:limit] + "…") if len(s) > limit else s


class _TraceWriter:
    """Boxed turn-by-turn view of the Agent SDK message stream.

    The Agent SDK splits one logical assistant turn across multiple
    `AssistantMessage` events (thinking, then tool_use, etc.). They share a
    `message_id`, so we coalesce them into a single boxed turn.
    """

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
                err = "  (ERROR)" if block.is_error else ""
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
                        self._buf_lines.append(f"  … (+{len(text) - 600:,} more chars)")
                self.flush()
        elif isinstance(msg, ResultMessage):
            self.flush()
            u = msg.usage or {}
            self._buf_kind = "RESULT"
            self._buf_lines = [
                f"stop_reason: {msg.stop_reason}",
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


async def run(url: str, use_oauth: bool = False, run_id: int | None = None) -> dict[str, Any]:
    if run_id is None:
        run_id = _next_run_id()
    TRACES_DIR.mkdir(exist_ok=True)
    trace_path = TRACES_DIR / f"run_{run_id:03d}.txt"
    trace = trace_path.open("w")
    def log(s: str) -> None:
        trace.write(s + "\n"); trace.flush()
    log(f"=== Agent SDK run {run_id:03d} ===")
    log(f"URL: {url}")
    log(f"started: {datetime.now(timezone.utc).isoformat()}")
    log(f"use_oauth: {use_oauth}")
    log("")

    saved = os.environ.pop("ANTHROPIC_API_KEY", None) if use_oauth else None
    server = create_sdk_mcp_server(name="fetcher", version="0.1.0", tools=[_fetch_url])
    options = ClaudeAgentOptions(
        model=MODEL,
        mcp_servers={"fetcher": server},
        # Allow Read and Bash so the model can actually use the offload
        # pointer (read the saved file, grep it, etc.) without prompts.
        allowed_tools=["mcp__fetcher__fetch_url", "Read", "Bash"],
        permission_mode="bypassPermissions",
    )

    parts: list[str] = []
    next_tokens: int | None = None
    saw_tool = False
    cost_usd: float | None = None
    total_usage: dict[str, Any] | None = None
    num_turns: int = 0
    writer = _TraceWriter(log)
    try:
        async for msg in query(prompt=PROMPT.format(url=url), options=options):
            writer.write(msg)
            if isinstance(msg, UserMessage):
                for block in msg.content:
                    if hasattr(block, "tool_use_id") and hasattr(block, "content"):
                        parts.append(_block_text(block.content))
                        saw_tool = True
            elif isinstance(msg, AssistantMessage):
                num_turns += 1
                if saw_tool and next_tokens is None:
                    u = getattr(msg, "usage", None)
                    if u is not None:
                        next_tokens = (
                            getattr(u, "input_tokens", None)
                            or (u.get("input_tokens") if isinstance(u, dict) else None)
                        )
            elif isinstance(msg, ResultMessage):
                cost_usd = getattr(msg, "total_cost_usd", None)
                total_usage = dict(msg.usage) if msg.usage else None
    finally:
        writer.flush()
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved
        log("")
        log(f"finished: {datetime.now(timezone.utc).isoformat()}")
        trace.close()

    text = "\n---\n".join(parts)
    # Cost at standard API rates, regardless of which channel actually billed.
    api_rate_cost = pricing.cost_usd(total_usage) if total_usage else None
    actual_cost = cost_usd  # what the harness reported as billed
    RESULTS_DIR.mkdir(exist_ok=True)
    result_path = RESULTS_DIR / f"run_{run_id:03d}.txt"
    actual_str = f"{actual_cost:.6f}" if actual_cost is not None else "n/a"
    api_str = f"{api_rate_cost:.6f}" if api_rate_cost is not None else "n/a"
    result_path.write_text(
        f"# Agent SDK run {run_id:03d}\n"
        f"# URL: {url}\n"
        f"# tool_result chars: {len(text):,}\n"
        f"# next-turn input_tokens: {next_tokens}\n"
        f"# turns: {num_turns}\n"
        f"# actual cost (USD, harness-reported): {actual_str}\n"
        f"# API-rate cost (USD, public Opus 4 prices): {api_str}\n"
        f"# total usage: {total_usage}\n"
        f"# ---\n{text or '(no tool_result captured)'}"
    )
    return {
        "tool_result_chars": len(text),
        "tool_result_text": text,
        "next_turn_input_tokens": next_tokens,
        "trace_path": str(trace_path),
        "result_path": str(result_path),
        "run_id": run_id,
        "cost_usd": actual_cost,
        "api_rate_cost_usd": api_rate_cost,
        "total_usage": total_usage,
        "num_turns": num_turns,
    }
