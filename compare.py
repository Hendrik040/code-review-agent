"""Orchestrator: invoke both SDK paths against the same URL and write what
each path put into the model's context to a file. The actual SDK code lives
in `agent_sdk/runner.py` and `client_sdk/runner.py` so the line counts can be
compared directly."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from agent_sdk import runner as agent_runner
from client_sdk import runner as client_runner

DEFAULT_URL = "https://en.wikipedia.org/wiki/Software_engineering"
USE_OAUTH = False  # set by --use-oauth CLI flag


def _fetch_raw_chars(url: str) -> int:
    return len(httpx.get(
        url, follow_redirects=True, timeout=30.0,
        headers={"User-Agent": "tool-offload-compare/0.1 httpx"},
    ).text)


def _fmt(n: int) -> str:
    return f"{n / 1024:.1f} KB ({n:,} chars)" if n >= 1024 else f"{n} chars"


_EMPTY = {
    "tool_result_chars": 0, "tool_result_text": "",
    "next_turn_input_tokens": None, "trace_path": None,
    "result_path": None, "run_id": None, "cost_usd": None,
    "total_usage": None, "num_turns": 0,
}


def _shared_run_id() -> int:
    """One run number for both SDKs so traces line up across folders."""
    return max(agent_runner._next_run_id(), client_runner._next_run_id())


async def main_async(url: str) -> None:
    load_dotenv(override=True)
    run_id = _shared_run_id()
    raw = _fetch_raw_chars(url)
    print(f"=== Run {run_id:03d} ===")
    print(f"URL: {url}")
    print(f"Raw fetch: {_fmt(raw)}\n")

    print(f"→ Agent SDK path (run {run_id:03d})...")
    try:
        a = await agent_runner.run(url, use_oauth=USE_OAUTH, run_id=run_id)
    except Exception as e:
        print(f"  failed: {type(e).__name__}: {e}")
        a = dict(_EMPTY)

    print(f"→ Client SDK path (run {run_id:03d})...")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  skipped: no ANTHROPIC_API_KEY (Client SDK has no OAuth path)")
        c = dict(_EMPTY)
    else:
        try:
            c = await asyncio.to_thread(client_runner.run, url, run_id)
        except Exception as e:
            print(f"  failed: {type(e).__name__}: {e}")
            c = dict(_EMPTY)

    print()
    print(
        f"{'':12} {'tool_result in ctx':>24}  {'turns':>5}  "
        f"{'in_tok':>9}  {'actual $':>9}  {'API-rate $':>10}"
    )
    print("-" * 80)
    for label, r in (("Agent SDK", a), ("Client SDK", c)):
        toks = "n/a" if r["next_turn_input_tokens"] is None else f"{r['next_turn_input_tokens']:,}"
        actual = "n/a" if r["cost_usd"] is None else f"${r['cost_usd']:.4f}"
        api = r.get("api_rate_cost_usd")
        api_s = "n/a" if api is None else f"${api:.4f}"
        # Client SDK's "API-rate" equals "actual" since it is the API.
        if "Client" in label and api is None:
            api_s = actual
        print(
            f"{label:12} {_fmt(r['tool_result_chars']):>24}  "
            f"{r['num_turns']:>5}  {toks:>9}  {actual:>9}  {api_s:>10}"
        )
    if a["cost_usd"] is not None and c["cost_usd"]:
        ratio = c["cost_usd"] / a["cost_usd"] if a["cost_usd"] else float("inf")
        a_api = a.get("api_rate_cost_usd")
        if a_api and abs(a_api - a["cost_usd"]) / max(a["cost_usd"], 1e-9) > 0.1:
            print(
                f"\n  → Agent SDK billed via Max OAuth at ${a['cost_usd']:.4f}; "
                f"would be ${a_api:.4f} at full API rates."
            )
            api_ratio = c["cost_usd"] / a_api
            print(
                f"  → apples-to-apples (both at API): Agent ${a_api:.4f}  vs  "
                f"Client ${c['cost_usd']:.4f}  ({api_ratio:.1f}× ratio)"
            )
        else:
            print(f"\n  → Cost ratio (Client / Agent): {ratio:.1f}×")

    print()
    for label, r in (("Agent SDK", a), ("Client SDK", c)):
        if r.get("result_path"):
            print(f"  {label}  result: {r['result_path']}")
        if r.get("trace_path"):
            print(f"  {label}  trace : {r['trace_path']}")


def main() -> None:
    global USE_OAUTH
    args = list(sys.argv[1:])
    if "--use-oauth" in args:
        USE_OAUTH = True
        args.remove("--use-oauth")
    url = args[0] if args else DEFAULT_URL
    asyncio.run(main_async(url))


if __name__ == "__main__":
    main()
