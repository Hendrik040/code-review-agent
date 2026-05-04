"""Parse trace files for tool-call distribution + token breakdowns.

Trace files live at <sdk>_sdk/traces/run_NNN.txt. Each turn block contains:

    │ tool_use: mcp__reviewer__<tool_name>
    │ usage: in=X cache_w=X cache_r=X out=X

We grep these out per sweep and roll up:

  tool_calls_total, by_tool[bash|read_file_section|grep|ast_search|...]
  tokens_input, tokens_cache_write, tokens_cache_read, tokens_output

Per-sweep summary written to sweep_<id>/tool_stats.json.

Usage:
    uv run python bugsinpy_bench/scripts/parse_traces.py \\
        bugsinpy_bench/results/sweep_2026-05-04_agent_low
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_TOOL_RE = re.compile(r"tool_use:\s+mcp__reviewer__(\w+)")
_USAGE_RE = re.compile(
    r"usage:\s+in=(\d+)\s+cache_w=(\d+)\s+cache_r=(\d+)\s+out=(\d+)"
)


def _parse_one(trace_path: Path) -> dict:
    text = trace_path.read_text(errors="replace")
    tools: Counter[str] = Counter()
    in_tok = cw_tok = cr_tok = out_tok = 0
    for line in text.splitlines():
        m = _TOOL_RE.search(line)
        if m:
            tools[m.group(1)] += 1
            continue
        m = _USAGE_RE.search(line)
        if m:
            in_tok += int(m.group(1))
            cw_tok += int(m.group(2))
            cr_tok += int(m.group(3))
            out_tok += int(m.group(4))
    return {
        "tools": dict(tools),
        "tokens": {
            "input": in_tok,
            "cache_write": cw_tok,
            "cache_read": cr_tok,
            "output": out_tok,
            "total_billable": in_tok + cw_tok + cr_tok + out_tok,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sweep", help="Path to sweep_<id>/ directory")
    args = ap.parse_args()
    sweep_dir = Path(args.sweep)
    if not sweep_dir.is_dir():
        sys.exit(f"not a directory: {sweep_dir}")
    meta_path = sweep_dir / "meta.json"
    if not meta_path.is_file():
        sys.exit(f"missing meta.json")
    meta = json.loads(meta_path.read_text())
    sdk = meta["sdk"]
    traces_dir = PROJECT_ROOT / f"{sdk}_sdk" / "traces"

    # We only have run_id stored in suite.md; map sweep run files to traces
    # by reading the prepended bench header that records bug labels.
    runs_dir = sweep_dir / "runs"
    per_bug: list[dict] = []
    tools_total: Counter[str] = Counter()
    tokens_total = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}

    for run_file in sorted(runs_dir.iterdir()):
        if not run_file.is_file():
            continue
        text = run_file.read_text()
        # Extract run id from the SDK's own header that follows the bench header.
        m = re.search(r"# Agent SDK reviewer run (\d+)|# Client SDK reviewer run (\d+)", text)
        if not m:
            continue
        run_id = int(m.group(1) or m.group(2))
        trace_file = traces_dir / f"run_{run_id:03d}.txt"
        if not trace_file.is_file():
            continue
        # Bug label from header.
        label_match = re.search(r"^# bug: (.+)$", text, flags=re.MULTILINE)
        label = label_match.group(1).strip() if label_match else f"run_{run_id}"
        parsed = _parse_one(trace_file)
        per_bug.append({"label": label, "run_id": run_id, **parsed})
        for t, c in parsed["tools"].items():
            tools_total[t] += c
        for k in tokens_total:
            tokens_total[k] += parsed["tokens"][k]

    summary = {
        "sweep_id": meta["sweep_id"],
        "sdk": sdk,
        "effort": meta["effort"],
        "n_runs": len(per_bug),
        "tool_calls_total": int(sum(tools_total.values())),
        "tool_calls_by_tool": dict(tools_total),
        "tokens": tokens_total,
        "per_bug": per_bug,
    }
    out_path = sweep_dir / "tool_stats.json"
    out_path.write_text(json.dumps(summary, indent=2))

    print(f"\n{sweep_dir.name}  (sdk={sdk} effort={meta['effort']}  n={len(per_bug)})")
    print(f"  total tool calls: {summary['tool_calls_total']}")
    if tools_total:
        for tool, count in tools_total.most_common():
            pct = 100 * count / summary["tool_calls_total"]
            print(f"    {tool:<25}  {count:>5}  ({pct:.0f}%)")
    print(f"  tokens: in={tokens_total['input']:,}  "
          f"cache_w={tokens_total['cache_write']:,}  "
          f"cache_r={tokens_total['cache_read']:,}  "
          f"out={tokens_total['output']:,}")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
