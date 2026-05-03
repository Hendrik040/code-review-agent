"""ODIS CLI — `python -m shared.odis_cli BASE..HEAD`.

Phase 4 moves ODIS execution to wherever the repo lives. The agent
invokes this CLI via `repo.exec(...)`, the algorithm runs next to the
repo (avoiding many file-content round trips over the wire), and the
final markdown context blob is what crosses back to the host.

Both backends invoke this the same way:

    python -m shared.odis_cli HEAD~1..HEAD

  - LocalRepo seeds PYTHONPATH so `shared/` resolves to the host
    package; `Path.cwd()` is the temp git repo.
  - DaytonaRepo: the sandbox image stages `shared/` at
    /opt/code-review-agent (PYTHONPATH set in the Dockerfile);
    cwd is /workspace/repo.

The CLI is intentionally tiny; everything interesting lives in
shared.odis.build_context.
"""

from __future__ import annotations

import sys
from pathlib import Path

from shared.odis import build_context


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(
            "usage: python -m shared.odis_cli BASE..HEAD\n"
            "  Emit the build_review_context() markdown for the diff "
            "between BASE and HEAD\n"
            "  in the current working directory's git repo. Output goes "
            "to stdout.",
            file=sys.stdout if args and args[0] in ("-h", "--help") else sys.stderr,
        )
        return 0 if args and args[0] in ("-h", "--help") else 2

    spec = args[0]
    if ".." not in spec:
        print(
            f"error: expected BASE..HEAD, got {spec!r}",
            file=sys.stderr,
        )
        return 2
    base, _, head = spec.partition("..")
    if not base or not head:
        print(
            f"error: empty base or head in {spec!r}",
            file=sys.stderr,
        )
        return 2

    try:
        markdown = build_context(Path.cwd(), base, head)
    except Exception as e:  # noqa: BLE001 — boundary; surface to stderr
        print(
            f"error: build_context failed ({type(e).__name__}): {e}",
            file=sys.stderr,
        )
        return 1

    sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
