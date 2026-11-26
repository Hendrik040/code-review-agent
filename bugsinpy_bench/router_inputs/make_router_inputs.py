"""Build router inputs for the model-tiers pilot.

For each bug in prepared_pilot30.json:
  <label>.diff          git diff --unified=3 --no-color base_ref..head_ref,
                        the same command build_review_context uses, with refs
                        from shared.fixtures.materialize_upstream.
  <label>.summary.json  one Claude Haiku 5.5 description per changed non-test
                        Python file, merged per bug.
Writes _haiku_cost.json with token totals and cost.

Run from repo root:  uv run python bugsinpy_bench/router_inputs/make_router_inputs.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import anthropic  # noqa: E402
from shared.fixtures import materialize_upstream  # noqa: E402

OUT = Path(__file__).resolve().parent
PREPARED = ROOT / "bugsinpy_bench" / "dataset" / "prepared_pilot30.json"
MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10e-6, 0.50e-6  # per token, prompts <= 100K

FIELDS = ["what_changed", "behavior_before_after", "interfaces_touched",
          "data_touched", "error_handling_changes"]
LIST = {"type": "array", "items": {"type": "string"}}
SCHEMA = {
    "type": "object",
    "properties": {
        "what_changed": {"type": "string"},
        "behavior_before_after": LIST,
        "interfaces_touched": LIST,
        "data_touched": LIST,
        "error_handling_changes": LIST,
    },
    "required": FIELDS,
    "additionalProperties": False,
}
SYSTEM = """You describe code changes. You are given the git diff of one source file.
Describe what the change does. Never judge it: do not mention bugs, risk, quality,
correctness, mistakes, or whether the change is good or bad. Plain description only.

Fields:
- what_changed: 1 or 2 plain sentences.
- behavior_before_after: one "before → after" string per behavior change.
- interfaces_touched: changed function signatures, endpoints, CLI flags or schemas.
- data_touched: stored data read or written differently.
- error_handling_changes: exceptions raised or caught differently.
Use an empty list when a field does not apply."""

TEST_RE = re.compile(r"(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|_tests?\.py$|(^|/)conftest\.py$")


def is_source_py(path: str) -> bool:
    return path.endswith(".py") and not TEST_RE.search(path)


def main() -> None:
    client = anthropic.Anthropic()
    entries = json.loads(PREPARED.read_text())
    tot = {"model": MODEL, "calls": 0, "input_tokens": 0, "output_tokens": 0}
    for e in entries:
        label = f"{e['project']}#{e['bug_id']}"
        stem = f"{e['project']}_{e['bug_id']}"
        with materialize_upstream(e["github_url"], e["introducing_commit"],
                                  name=f"router-{stem}") as (repo, base, head):
            rng = f"{base}..{head}"
            diff = repo.exec(f"git diff --unified=3 --no-color {rng}", timeout=120).stdout
            names = repo.exec(f"git diff --name-only {rng}", timeout=60).stdout.split()
            per_file = {}
            for f in [n for n in names if is_source_py(n)]:
                fdiff = repo.exec(f"git diff --unified=3 --no-color {rng} -- '{f}'", timeout=60).stdout
                resp = client.messages.create(
                    model=MODEL, max_tokens=4096, system=SYSTEM,
                    messages=[{"role": "user", "content": f"File: {f}\n\n```diff\n{fdiff}\n```"}],
                    output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
                )
                tot["calls"] += 1
                tot["input_tokens"] += resp.usage.input_tokens
                tot["output_tokens"] += resp.usage.output_tokens
                text = next(b.text for b in resp.content if b.type == "text")
                per_file[f] = json.loads(text)
        (OUT / f"{stem}.diff").write_text(diff)
        merged = {
            "what_changed": "\n".join(f"{f}: {s['what_changed']}" for f, s in per_file.items()),
            **{k: [x for s in per_file.values() for x in s[k]] for k in FIELDS[1:]},
        }
        (OUT / f"{stem}.summary.json").write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
        print(f"{label}: {len(per_file)} source file(s), diff {len(diff)} chars", flush=True)
    tot["cost_usd"] = round(tot["input_tokens"] * PRICE_IN + tot["output_tokens"] * PRICE_OUT, 4)
    (OUT / "_haiku_cost.json").write_text(json.dumps(tot, indent=2) + "\n")
    print(tot)


if __name__ == "__main__":
    main()
