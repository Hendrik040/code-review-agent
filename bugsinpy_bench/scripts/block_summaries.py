"""Per-block change records for block-level Jev routing (design section 1).

Haiku 5.5 at effort high reads each changed file's diff and returns one
record per changed code block: what kind of block, what it did before and
after, which callers or users the diff shows it touching, which constructs
the change involves, and a 1-10 complexity score (used by arm B only). It
describes and never judges correctness.

Results are cached per diff SHA-256, so the router and reruns pay nothing.

Usage:
    .venv/bin/python bugsinpy_bench/scripts/block_summaries.py --set bugsinpy [--only a#1,b#2]
    .venv/bin/python bugsinpy_bench/scripts/block_summaries.py --set martian
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from router_inputs import fetch_diff, split_files  # noqa: E402

MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10, 0.50  # USD per MTok
CACHE_DIR = ROOT / "bugsinpy_bench" / "router_inputs" / "blocks"
BUGSINPY_DIFFS = ROOT / "bugsinpy_bench" / "router_inputs"
MARTIAN_DIFFS = ROOT / "martian_bench" / "routing" / "diffs"
MAX_BLOCKS = 40
MAX_CHUNK = 24_000

KINDS = ["data_structure", "function", "method", "class", "config", "test", "call_site", "import", "other"]
CONSTRUCTS = [
    "regex", "slicing", "comparison", "range_bound", "format_string", "loop", "recursion",
    "counter_or_stack", "cache", "flag", "mutable_default", "exception", "early_return",
    "return_value", "signature", "type_conversion", "none_handling", "numeric", "string_bytes",
    "datetime", "async", "callback", "thread_or_process", "io", "sql_or_query", "config_value",
    "logging", "test_assertion",
]

SYSTEM = (
    "You describe code changes for a routing system. Split the diff into the code blocks it "
    "changes and describe each one factually. Never judge the change: do not say whether it is "
    "correct, buggy, risky, good or bad. Use only what the diff shows."
)

USER_TEMPLATE = """Pull request title: {title}
File: {path}

<diff>
{diff}
</diff>

Return one record per changed code block in this file (a function, method, class, data
structure, configuration block, test, import group, or a call site whose arguments changed).
For each record:
- kind: one of {kinds}
- symbol: the block's name (function, class, key or test name), or "" if none
- lines_added, lines_removed: changed lines that belong to this block
- before: what this block did before the change, in one or two plain sentences ("" if new)
- after: what it does after the change, in one or two plain sentences ("" if deleted)
- callers_or_users_touched: callers, users or overriders of this block visible in the diff
- constructs: the constructs the changed lines involve, from: {constructs}
- complexity_1_10: how hard the changed lines are to verify, 1 = trivial, 10 = hardest
If the file has no changed code blocks, return an empty list."""

SCHEMA = {
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": KINDS},
                    "symbol": {"type": "string"},
                    "lines_added": {"type": "integer"},
                    "lines_removed": {"type": "integer"},
                    "before": {"type": "string"},
                    "after": {"type": "string"},
                    "callers_or_users_touched": {"type": "array", "items": {"type": "string"}},
                    "constructs": {"type": "array", "items": {"type": "string", "enum": CONSTRUCTS}},
                    "complexity_1_10": {"type": "integer"},
                },
                "required": ["kind", "symbol", "lines_added", "lines_removed", "before", "after",
                             "callers_or_users_touched", "constructs", "complexity_1_10"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["blocks"],
    "additionalProperties": False,
}


def numstat(diff: str) -> list[dict]:
    """Lines added and removed per file, from a unified diff."""
    out = []
    for path, chunk in split_files(diff).items():
        added = removed = 0
        for line in chunk.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        out.append({"path": path, "added": added, "removed": removed})
    return out


def _chunks(file_diff: str) -> list[str]:
    """Split a file diff at hunk boundaries into pieces of at most MAX_CHUNK characters."""
    if len(file_diff) <= MAX_CHUNK:
        return [file_diff]
    parts = re.split(r"(?m)^(?=@@ )", file_diff)
    head, hunks = parts[0], parts[1:]
    out, cur = [], head
    for h in hunks:
        if len(cur) + len(h) > MAX_CHUNK and cur != head:
            out.append(cur)
            cur = head
        cur += h[:MAX_CHUNK]
    out.append(cur)
    return out


def extract_file(client, title: str, path: str, file_diff: str) -> tuple[list[dict], dict]:
    """Ask Haiku for this file's block records. Returns (blocks, usage)."""
    blocks, tin, tout = [], 0, 0
    for part in _chunks(file_diff):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": USER_TEMPLATE.format(
                title=title, path=path, diff=part, kinds=", ".join(KINDS),
                constructs=", ".join(CONSTRUCTS))}],
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        blocks += json.loads(text)["blocks"]
        tin += resp.usage.input_tokens
        tout += resp.usage.output_tokens
    for i, b in enumerate(blocks):
        b["file"] = path
        b["block_id"] = f"{path}::{b.get('symbol', '')}::{i}"
    return blocks, {"input_tokens": tin, "output_tokens": tout}


def get_blocks(client, title: str, diff: str, *, cache_dir: Path) -> dict:
    """All block records for a diff, cached by the diff's SHA-256."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{hashlib.sha256(diff.encode()).hexdigest()}.json"
    if path.exists():
        return {**json.loads(path.read_text()), "cached": True}
    blocks, tin, tout = [], 0, 0
    for fpath, fdiff in split_files(diff).items():
        b, u = extract_file(client, title, fpath, fdiff)
        blocks += b
        tin += u["input_tokens"]
        tout += u["output_tokens"]
    blocks.sort(key=lambda b: b["lines_added"] + b["lines_removed"], reverse=True)
    kept, dropped = blocks[:MAX_BLOCKS], max(0, len(blocks) - MAX_BLOCKS)
    usage = {"input_tokens": tin, "output_tokens": tout,
             "cost_usd": round((tin * PRICE_IN + tout * PRICE_OUT) / 1e6, 6)}
    rec = {"title": title, "blocks": kept, "blocks_dropped": dropped, "usage": usage}
    path.write_text(json.dumps(rec, indent=1) + "\n")
    return {**rec, "cached": False}


def _martian_diff(e: dict) -> str:
    base, head = e["base_sha"], e["head_sha"]
    with tempfile.TemporaryDirectory(prefix="blocks-martian-") as d:
        subprocess.run(
            "git init -q && "
            f"git remote add origin {shlex.quote(e['github_url'])} && "
            f"git -c protocol.version=2 fetch -q --depth 1 --no-tags origin {shlex.quote(base)} {shlex.quote(head)}",
            shell=True, cwd=d, check=True, capture_output=True, timeout=1200,
        )
        return subprocess.run(f"git diff --unified=3 --no-color {base}..{head}", shell=True, cwd=d,
                              check=True, capture_output=True, text=True, timeout=300).stdout


def load_entries(which: str) -> list[dict]:
    """[{label, title, diff}] for a benchmark set; diffs are fetched once and stored."""
    out = []
    if which == "bugsinpy":
        for f in ("prepared_pilot30.json", "prepared_rest70.json"):
            for e in json.loads((ROOT / "bugsinpy_bench" / "dataset" / f).read_text()):
                p = BUGSINPY_DIFFS / f"{e['project']}_{e['bug_id']}.diff"
                if not p.exists():
                    p.write_text(fetch_diff(e))
                title = (e.get("introducer_message") or "").splitlines()[0] if e.get("introducer_message") else ""
                out.append({"label": f"{e['project']}#{e['bug_id']}", "title": title, "diff": p.read_text()})
    elif which == "martian":
        MARTIAN_DIFFS.mkdir(parents=True, exist_ok=True)
        for e in json.loads((ROOT / "martian_bench" / "dataset" / "prepared_martian.json").read_text()):
            label = f"{e['repo_slug'].replace('/', '_')}#{e['pr_number']}"
            p = MARTIAN_DIFFS / f"{label.replace('#', '_')}.diff"
            if not p.exists():
                p.write_text(_martian_diff(e))
            out.append({"label": label, "title": e.get("title") or "", "diff": p.read_text()})
    else:
        raise ValueError(which)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, choices=["bugsinpy", "martian"])
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    from dotenv import load_dotenv
    from anthropic import Anthropic

    load_dotenv(ROOT / ".env")
    client = Anthropic()
    entries = load_entries(args.set)
    if args.only:
        keep = set(args.only.split(","))
        entries = [e for e in entries if e["label"] in keep]

    def one(e):
        r = get_blocks(client, e["title"], e["diff"], cache_dir=CACHE_DIR)
        print(f"{e['label']:48s} blocks={len(r['blocks']):3d} dropped={r['blocks_dropped']} "
              f"cached={r['cached']} ${r['usage']['cost_usd']:.4f}", flush=True)
        return r

    with ThreadPoolExecutor(args.workers) as ex:
        results = list(ex.map(one, entries))
    new = [r for r in results if not r["cached"]]
    cost = sum(r["usage"]["cost_usd"] for r in new)
    log = CACHE_DIR / "_cost.json"
    hist = json.loads(log.read_text()) if log.exists() else []
    hist.append({"set": args.set, "only": args.only, "new_diffs": len(new), "model": MODEL,
                 "effort": "high", "input_tokens": sum(r["usage"]["input_tokens"] for r in new),
                 "output_tokens": sum(r["usage"]["output_tokens"] for r in new), "cost_usd": round(cost, 6)})
    log.write_text(json.dumps(hist, indent=2) + "\n")
    print(f"TOTAL new={len(new)} cost=${cost:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
