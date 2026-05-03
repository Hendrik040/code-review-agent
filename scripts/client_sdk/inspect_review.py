"""Materialize contract_mismatch and run the Client SDK reviewer
end-to-end. Prints what the reviewer returned, plus the trace + result
file paths so you can read them after.

Run:    uv run python scripts/inspect_review.py
Cost:   one model call, ~$0.10-0.15 at standard Opus 4 rates.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client_sdk import reviewer
from shared.fixtures import CONTRACT_MISMATCH, materialize


def main() -> None:
    with materialize(CONTRACT_MISMATCH) as fx:
        result = reviewer.run(fx.repo_path, fx.base_ref, fx.head_ref)

    expected = CONTRACT_MISMATCH.expected[0]
    matched = [
        f for f in result["findings"]
        if f.file == expected.file and f.category == expected.category
    ]

    print("=" * 64)
    print(f"  RUN #{result['run_id']}")
    print("=" * 64)
    print(f"turns:        {result['num_turns']}")
    print(f"cost (USD):   ${result['cost_usd']:.4f}")
    print(f"usage:        {result['total_usage']}")
    print(f"findings:     {len(result['findings'])}")
    print(f"trace file:   {result['trace_path']}")
    print(f"result file:  {result['result_path']}")
    print()

    print("=" * 64)
    print("  FINDINGS")
    print("=" * 64)
    for i, f in enumerate(result["findings"], 1):
        print(f"\n[{i}] {f.severity}/{f.category}  {f.file}:{f.line}")
        print(f"    summary: {f.summary}")
        print(f"    detail:  {f.detail[:240]}{'…' if len(f.detail) > 240 else ''}")
        if f.suggested_fix:
            preview = f.suggested_fix[:240]
            print(f"    fix:     {preview}{'…' if len(f.suggested_fix) > 240 else ''}")

    print()
    print("=" * 64)
    print("  EXPECTED-MATCH CHECK")
    print("=" * 64)
    print(f"  expected: {expected.file} / {expected.category}")
    print(f"  matches:  {len(matched)}")
    if matched:
        print(f"  -> {matched[0].file}:{matched[0].line}  {matched[0].summary[:80]}")


if __name__ == "__main__":
    main()
