"""Materialize contract_mismatch and print the ODIS-curated context
the reviewer will hand to the model. No model call, no API spend —
just the input shape.

Run:    uv run python scripts/inspect_odis.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.fixtures import CONTRACT_MISMATCH, materialize
from shared.odis import build_context


def main() -> None:
    with materialize(CONTRACT_MISMATCH) as fx:
        ctx = build_context(fx.repo_path, fx.base_ref, fx.head_ref)

    print(ctx)
    print()
    print("=" * 60)
    print(f"context length: {len(ctx):,} chars")
    print("=" * 60)
    print()
    print("Sections to look for in the output above:")
    print("  1. <diff>           — only calc.py, as expected")
    print("  2. <file changed>   — calc.py with line numbers, full def")
    print("  3. <callees>        — should be 'None' (add doesn't call anything)")
    print("  4. <callers>        — main.py with `x = add(1, 2)` visible")
    print()
    print("That last block is the crux: main.py wasn't in the diff, but ODIS")
    print("pulled it in because it CALLS the changed symbol `add`.")


if __name__ == "__main__":
    main()
