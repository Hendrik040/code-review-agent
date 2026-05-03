"""Materialize the contract_mismatch fixture and dump everything you'd
want to see about it: repo path, git log, files, the diff ODIS will
process, and the expected Finding. Used by the manual test plan, but
re-runnable any time you want to peek at the fixture state.

Run:    uv run python scripts/inspect_fixture.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Project root on path so `shared.*` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.fixtures import CONTRACT_MISMATCH, materialize


def main() -> None:
    with materialize(CONTRACT_MISMATCH) as fx:
        print(f"=== fixture name:  {fx.name}")
        print(f"=== repo_path:     {fx.repo_path}")
        print(f"=== refs:          {fx.base_ref}..{fx.head_ref}")
        print(f"=== expected:      {len(fx.expected)} finding(s)")
        print()

        print("=== git log (the two commits) ===")
        print(subprocess.check_output(
            ["git", "-C", str(fx.repo_path), "log", "--oneline"],
        ).decode())

        print("=== files at HEAD ===")
        for p in sorted(fx.repo_path.iterdir()):
            if p.is_file() and p.suffix == ".py":
                print(f"  {p.name}")
        print()

        print("=== diff base..head (what ODIS will see) ===")
        print(subprocess.check_output(
            ["git", "-C", str(fx.repo_path), "diff", "--unified=1", "HEAD~1..HEAD"],
        ).decode())

        print("=== expected Finding (what a competent reviewer should report) ===")
        f = fx.expected[0]
        print(f"  file:     {f.file}")
        print(f"  line:     {f.line}")
        print(f"  category: {f.category}")
        print(f"  severity: {f.severity}")
        print(f"  summary:  {f.summary}")


if __name__ == "__main__":
    main()
