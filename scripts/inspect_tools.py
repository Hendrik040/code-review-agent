"""Materialize contract_mismatch and exercise each of the three
investigation tools the reviewer offers to the model. No API.

Run:    uv run python scripts/inspect_tools.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.agent_tools import ast_search, grep, read_file_section
from shared.fixtures import CONTRACT_MISMATCH, materialize


def banner(title: str) -> None:
    print()
    print("=" * 64)
    print(f"  {title}")
    print("=" * 64)


def main() -> None:
    with materialize(CONTRACT_MISMATCH) as fx:
        repo = fx.repo_path

        banner("read_file_section(main.py, 1, 7)")
        print("Purpose: pure I/O — read N lines of a file in the repo.")
        print(read_file_section(repo, "main.py", 1, 7))

        banner("ast_search('add($$$)', python)")
        print("Purpose: structural search — find every call to `add` regardless")
        print("of arity, whitespace, or formatting. `$$$` matches any sequence.")
        print(ast_search(repo, "add($$$)", "python"))

        banner("ast_search('def $NAME($$$): $$$', python)")
        print("Purpose: find any function definition. `$NAME` captures the name.")
        print(ast_search(repo, "def $NAME($$$): $$$", "python"))

        banner("grep('def add', '*.py')")
        print("Purpose: plain regex fallback when AST patterns don't fit.")
        print(grep(repo, "def add", "*.py"))

        banner("read_file_section(missing.py, 1, 5) — error path")
        print("Purpose: confirm bad input returns a string, doesn't crash.")
        print(read_file_section(repo, "missing.py", 1, 5))


if __name__ == "__main__":
    main()
