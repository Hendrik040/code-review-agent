"""Client SDK path: fetch_url declared as a tool schema, driven through a
manual `client.messages.create` loop. Returns what the model received as
tool_result, plus the next-turn input_tokens. Writes a per-iteration trace of
the request/response back-and-forth to `traces/run_NNN.txt`."""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pricing  # noqa: E402

MODEL = "claude-opus-4-7"
PROMPT = (
    "Use the fetch_url tool to fetch {url}. Then write a 2-3 sentence "
    "summary of what the page is about."
)
UA = "tool-offload-compare/0.1 httpx"
MAX_TOKENS = 1024
TRACES_DIR = Path(__file__).parent / "traces"
RESULTS_DIR = Path(__file__).parent / "results"

TOOL_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "fetch_url",
        "description": "Fetch a URL via HTTP GET and return the body as text.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        # Cache the tools array. Anthropic prompt caching keys on prefix
        # equality, so the second call's tool prefix is a cache hit.
        "cache_control": {"type": "ephemeral"},
    }
]


def _fetch_url(url: str) -> str:
    return httpx.get(
        url, follow_redirects=True, timeout=30.0,
        headers={"User-Agent": UA},
    ).text


def _next_run_id() -> int:
    TRACES_DIR.mkdir(exist_ok=True)
    used = [int(m.group(1)) for p in TRACES_DIR.glob("run_*.txt")
            if (m := re.match(r"run_(\d+)\.txt$", p.name))]
    return (max(used) + 1) if used else 1


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


def _request_box_lines(messages: list[dict[str, Any]]) -> list[str]:
    lines = [f"messages: {len(messages)}"]
    for i, m in enumerate(messages):
        role, content = m["role"], m["content"]
        if isinstance(content, str):
            prev = (content[:120] + "…") if len(content) > 120 else content
            lines.append(f"  [{i}] {role}: {prev}")
        else:
            for blk in content:
                btype = blk.get("type") if isinstance(blk, dict) else getattr(blk, "type", "?")
                if btype == "tool_result":
                    body = blk["content"] if isinstance(blk, dict) else getattr(blk, "content", "")
                    chars = len(body) if isinstance(body, str) else 0
                    bid = blk["tool_use_id"] if isinstance(blk, dict) else blk.tool_use_id
                    lines.append(f"  [{i}] {role}: tool_result id={bid} chars={chars:,}")
                elif btype == "text":
                    text = blk["text"] if isinstance(blk, dict) else blk.text
                    prev = (text[:120] + "…") if len(text) > 120 else text
                    lines.append(f"  [{i}] {role}: text  {prev}")
                elif btype == "tool_use":
                    name = blk["name"] if isinstance(blk, dict) else blk.name
                    inp = blk["input"] if isinstance(blk, dict) else blk.input
                    lines.append(f"  [{i}] {role}: tool_use {name}({_short_args(inp)})")
    return lines


def _response_box_lines(response: Any) -> list[str]:
    u = response.usage
    lines = [
        f"stop_reason: {response.stop_reason}",
        f"usage: in={u.input_tokens} out={u.output_tokens}",
    ]
    for blk in response.content:
        if blk.type == "text":
            lines.append("")
            lines.append("text:")
            for tline in (blk.text or "").splitlines() or [""]:
                lines.append(f"  {tline}")
        elif blk.type == "tool_use":
            lines.append("")
            lines.append(f"tool_use: {blk.name}")
            lines.append(f"  args: {_short_args(blk.input)}")
    return lines


def run(url: str, run_id: int | None = None) -> dict[str, Any]:
    if run_id is None:
        run_id = _next_run_id()
    TRACES_DIR.mkdir(exist_ok=True)
    trace_path = TRACES_DIR / f"run_{run_id:03d}.txt"
    trace = trace_path.open("w")
    def log(s: str) -> None:
        trace.write(s + "\n"); trace.flush()
    log(f"=== Client SDK run {run_id:03d} ===")
    log(f"URL: {url}")
    log(f"started: {datetime.now(timezone.utc).isoformat()}")
    log("")

    client = anthropic.Anthropic()
    # Use a content-block list (not a bare string) so we can attach
    # cache_control later if we want. The prompt itself is short and likely
    # below the cache threshold, but this makes the structure consistent.
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [{"type": "text", "text": PROMPT.format(url=url)}],
        },
    ]
    parts: list[str] = []
    next_tokens: int | None = None
    total_usage = {
        "input_tokens": 0, "output_tokens": 0,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
    }
    num_turns = 0

    turn = 0
    try:
        for iteration in range(1, 6):
            turn += 1
            _draw_box(log, f"TURN {turn:02d}  [request]", _request_box_lines(messages))
            response = client.messages.create(
                model=MODEL, max_tokens=MAX_TOKENS,
                tools=TOOL_SCHEMA, messages=messages,
            )
            turn += 1
            _draw_box(log, f"TURN {turn:02d}  [response]", _response_box_lines(response))
            num_turns += 1
            for k in total_usage:
                total_usage[k] += getattr(response.usage, k, 0) or 0

            if response.stop_reason != "tool_use":
                if parts and next_tokens is None:
                    next_tokens = response.usage.input_tokens
                break

            messages.append({"role": "assistant", "content": response.content})
            results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use" and block.name == "fetch_url":
                    body = _fetch_url(block.input["url"])
                    turn += 1
                    _draw_box(log, f"TURN {turn:02d}  [tool_exec]", [
                        f"fetch_url({block.input['url']!r})",
                        f"-> {len(body):,} chars",
                    ])
                    parts.append(body)
                    # No cache_control here: the tool_result is sent once and
                    # there's no subsequent turn to read from cache, so a
                    # cache write would cost more than it saves.
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": body,
                    })
            messages.append({"role": "user", "content": results})
    finally:
        log("")
        log(f"finished: {datetime.now(timezone.utc).isoformat()}")
        trace.close()

    text = "\n---\n".join(parts)
    cost_usd = pricing.cost_usd(total_usage)
    RESULTS_DIR.mkdir(exist_ok=True)
    result_path = RESULTS_DIR / f"run_{run_id:03d}.txt"
    result_path.write_text(
        f"# Client SDK run {run_id:03d}\n"
        f"# URL: {url}\n"
        f"# tool_result chars: {len(text):,}\n"
        f"# next-turn input_tokens: {next_tokens}\n"
        f"# turns: {num_turns}\n"
        f"# total cost (USD): {cost_usd:.6f}\n"
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
        "cost_usd": cost_usd,
        "total_usage": total_usage,
        "num_turns": num_turns,
    }
