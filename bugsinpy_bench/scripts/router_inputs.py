"""Router inputs for the model-tiers pilot.

For each bug in a prepared file, write:
  bugsinpy_bench/router_inputs/<project>_<bug_id>.diff
      the review diff exactly as the reviewer saw it (ODIS's own
      `git diff --unified=3 --no-color base..head`, head = introducing
      commit, base = its parent)
  bugsinpy_bench/router_inputs/<project>_<bug_id>.summary.json
      one Haiku summary per changed non-test Python file, merged per bug.
      Haiku is told to describe the change and never judge it.

Usage:
    uv run python bugsinpy_bench/scripts/router_inputs.py \
        bugsinpy_bench/dataset/prepared_pilot30.json [--diffs-only]
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

OUT_DIR = PROJECT_ROOT / "bugsinpy_bench" / "router_inputs"
SUMMARY_MODEL = "claude-haiku-5-5"
# Haiku 5.5 list price, USD per million tokens (input, output).
HAIKU_IN, HAIKU_OUT = 0.10, 0.50  # prompts up to 100K tokens

SYSTEM = (
    "You describe code changes for a routing system. Describe only what the "
    "diff changes. Never judge it: do not mention bugs, risk, quality, "
    "correctness, style, or whether the change is good or bad. Be concrete "
    "and brief. Use empty lists when a category does not apply."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "what_changed": {"type": "string"},
        "behavior_before_after": {"type": "array", "items": {"type": "string"}},
        "interfaces_touched": {"type": "array", "items": {"type": "string"}},
        "data_touched": {"type": "array", "items": {"type": "string"}},
        "error_handling_changes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "what_changed",
        "behavior_before_after",
        "interfaces_touched",
        "data_touched",
        "error_handling_changes",
    ],
    "additionalProperties": False,
}

USER_TEMPLATE = """File: {path}

Diff of this file:
<diff>
{diff}
</diff>

Fill the fields:
- what_changed: 1 or 2 plain sentences.
- behavior_before_after: one "before → after" string per behavior change.
- interfaces_touched: changed function signatures, endpoints, CLI flags or schemas.
- data_touched: stored data read or written differently.
- error_handling_changes: exceptions raised or caught differently."""


def _label(e: dict) -> str:
    return f"{e['project']}#{e['bug_id']}"


def _stem(e: dict) -> str:
    return f"{e['project']}_{e['bug_id']}"


def _sh(cmd: str, cwd: Path) -> str:
    return subprocess.run(
        cmd, shell=True, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def fetch_diff(e: dict) -> str:
    head = e["introducing_commit"]
    with tempfile.TemporaryDirectory(prefix="router-") as tmp:
        d = Path(tmp)
        _sh(
            "git init -q && "
            f"git remote add origin {shlex.quote(e['github_url'])} && "
            f"git -c protocol.version=2 fetch -q --depth 2 --no-tags origin {shlex.quote(head)} && "
            f"git checkout -q {shlex.quote(head)}",
            d,
        )
        return _sh(f"git diff --unified=3 --no-color {head}^..{head}", d)


def split_files(diff: str) -> dict[str, str]:
    files: dict[str, str] = {}
    for chunk in re.split(r"(?m)^(?=diff --git )", diff):
        m = re.match(r"diff --git a/(\S+) b/(\S+)", chunk)
        if m:
            files[m.group(2)] = chunk
    return files


def is_source(path: str) -> bool:
    if not path.endswith(".py"):
        return False
    parts = path.split("/")
    name = parts[-1]
    return not (
        "tests" in parts
        or "test" in parts
        or "testing" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def summarize(client, path: str, file_diff: str) -> tuple[dict, int, int]:
    resp = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=1500,
        system=SYSTEM,
        messages=[{"role": "user", "content": USER_TEMPLATE.format(path=path, diff=file_diff)}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return json.loads(text), resp.usage.input_tokens, resp.usage.output_tokens


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prepared")
    ap.add_argument("--diffs-only", action="store_true")
    args = ap.parse_args()

    entries = json.loads(Path(args.prepared).read_text())
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    client = None
    if not args.diffs_only:
        from anthropic import Anthropic

        client = Anthropic()

    tot_in = tot_out = calls = 0
    for e in entries:
        diff_path = OUT_DIR / f"{_stem(e)}.diff"
        if not diff_path.exists():
            diff_path.write_text(fetch_diff(e))
        diff = diff_path.read_text()
        src = {p: d for p, d in split_files(diff).items() if is_source(p)}
        print(f"{_label(e)}: {len(split_files(diff))} files, {len(src)} source", flush=True)
        if args.diffs_only:
            continue

        merged = {
            "label": _label(e),
            "files": list(src),
            "what_changed": "",
            "behavior_before_after": [],
            "interfaces_touched": [],
            "data_touched": [],
            "error_handling_changes": [],
        }
        parts = []
        for path, fd in src.items():
            s, i, o = summarize(client, path, fd)
            tot_in, tot_out, calls = tot_in + i, tot_out + o, calls + 1
            parts.append(f"{path}: {s['what_changed']}")
            for k in ("behavior_before_after", "interfaces_touched", "data_touched", "error_handling_changes"):
                merged[k].extend(s[k])
        merged["what_changed"] = "\n".join(parts)
        (OUT_DIR / f"{_stem(e)}.summary.json").write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")

    if not args.diffs_only:
        cost = (tot_in * HAIKU_IN + tot_out * HAIKU_OUT) / 1_000_000
        meta = {
            "model": SUMMARY_MODEL,
            "calls": calls,
            "input_tokens": tot_in,
            "output_tokens": tot_out,
            "cost_usd": round(cost, 6),
            "rates_usd_per_mtok": {"input": HAIKU_IN, "output": HAIKU_OUT},
        }
        (OUT_DIR / "_summary_cost.json").write_text(json.dumps(meta, indent=2) + "\n")
        print(json.dumps(meta), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
