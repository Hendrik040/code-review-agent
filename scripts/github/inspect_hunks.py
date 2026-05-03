"""Print the parsed diff hunks for a PR. Verifies pr_fetch end-to-end.

Usage:
    uv run python scripts/github/inspect_hunks.py <pr_url>
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from github import pr_fetch


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: inspect_hunks.py <pr_url>")
    pr = pr_fetch.fetch_pr(sys.argv[1])
    hunks = pr_fetch.fetch_diff_hunks(pr.owner, pr.repo, pr.number)
    print(f"PR {pr.owner}/{pr.repo}#{pr.number}: {len(hunks)} files with hunks\n")
    for fname, hs in sorted(hunks.items()):
        print(f"  {fname}")
        for h in hs:
            print(f"    line {h.start_line}-{h.end_line} ({h.side})")


if __name__ == "__main__":
    main()
