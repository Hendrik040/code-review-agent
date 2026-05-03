"""Print the rendered analysis trail bullets for a given run.

Usage:
    uv run python scripts/github/inspect_trail.py <run_id>
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from github import trace_extract


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: inspect_trail.py <run_id>")
    run_id = int(sys.argv[1])
    trace_path = PROJECT_ROOT / "agent_sdk" / "traces" / f"run_{run_id:03d}.txt"
    if not trace_path.exists():
        sys.exit(f"trace file not found: {trace_path}")
    trail = trace_extract.extract_trail(trace_path)
    if not trail.bullets:
        print("(empty trail — file unparseable or no recognized tool calls)")
        return
    print(f"Trail for run #{run_id} ({len(trail.bullets)} bullets):\n")
    if trail.tool_summary:
        print(trail.tool_summary)
        print()
    for b in trail.bullets:
        print(f"  - {b}")


if __name__ == "__main__":
    main()
