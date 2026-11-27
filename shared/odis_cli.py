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

import dataclasses
import json
import re
import sys
import time
from pathlib import Path

from shared import impact
from shared.odis import Collected, ImpactCandidate, build_context, collect, render_markdown

# Phase 8 two-step mode. The host (shared/agent_tools.py) runs `collect`,
# decides a tier per impact candidate (with Jev, outside the sandbox),
# uploads the decisions, then runs `render`. Working files live under
# .git/odis/ so `git status` and `git grep` never see them; each call has
# its own token so two calls in one review cannot mix.
_TOKEN = re.compile(r"[a-z0-9]{8,32}")
_WORKDIR = Path(".git") / "odis"
# Files older than this belong to a call that never reached render
# (crash, timeout); a live call finishes within the tool's 30 s timeouts.
_STALE_S = 600


def _purge_stale() -> None:
    now = time.time()
    for f in _WORKDIR.glob("*.json"):
        try:
            if now - f.stat().st_mtime > _STALE_S:
                f.unlink()
        except OSError:
            pass


def _split_range(spec: str) -> tuple[str, str] | None:
    base, sep, head = spec.partition("..")
    return (base, head) if sep and base and head else None


def _collect(token: str, spec: str) -> int:
    refs = _split_range(spec)
    if refs is None:
        print(f"error: expected BASE..HEAD, got {spec!r}", file=sys.stderr)
        return 2
    try:
        c = collect(Path.cwd(), *refs)
    except Exception as e:  # noqa: BLE001 — boundary; surface to stderr
        print(f"error: build_context failed ({type(e).__name__}): {e}", file=sys.stderr)
        return 1
    try:
        _WORKDIR.mkdir(parents=True, exist_ok=True)
        _purge_stale()
    except OSError as e:  # e.g. .git is a file (worktree / submodule)
        print(f"error: cannot write {_WORKDIR}: {e}", file=sys.stderr)
        return 1
    (_WORKDIR / f"{token}.collected.json").write_text(json.dumps(dataclasses.asdict(c)))
    doc = {
        "diff": c.diff,
        "changed_chars": sum(len(x["text"]) for x in c.changed),
        "candidates": [
            {
                "id": x.id,
                "size": len(x.text),
                "summary": impact.summary(x),
                "facts": {
                    "same_file_as_change": x.same_file_as_change,
                    "imported_by_changed_file": x.imported_by_changed_file,
                    "is_test": x.is_test,
                },
            }
            for x in c.candidates
        ],
    }
    sys.stdout.write(json.dumps(doc))
    return 0


def _render(token: str) -> int:
    collected = _WORKDIR / f"{token}.collected.json"
    decisions = _WORKDIR / f"{token}.decisions.json"
    try:
        raw = json.loads(collected.read_text())
        dec = json.loads(decisions.read_text())
        c = Collected(
            diff=raw["diff"], changed=raw["changed"],
            candidates=[ImpactCandidate(**x) for x in raw["candidates"]],
        )
        markdown = render_markdown(
            c, dec.get("tiers"), note=dec.get("note", ""),
            drop_changed=bool(dec.get("drop_changed", False)),
        )
    except Exception as e:  # noqa: BLE001 — boundary; surface to stderr
        print(f"error: render failed ({type(e).__name__}): {e}", file=sys.stderr)
        return 1
    finally:
        for f in (collected, decisions):
            f.unlink(missing_ok=True)
        try:
            _WORKDIR.rmdir()
        except OSError:
            pass  # not empty (another call's files) or already gone
    sys.stdout.write(markdown)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(
            "usage: python -m shared.odis_cli BASE..HEAD\n"
            "       python -m shared.odis_cli collect TOKEN BASE..HEAD\n"
            "       python -m shared.odis_cli render TOKEN\n"
            "  Emit the build_review_context() markdown for the diff "
            "between BASE and HEAD\n"
            "  in the current working directory's git repo. Output goes "
            "to stdout.",
            file=sys.stdout if args and args[0] in ("-h", "--help") else sys.stderr,
        )
        return 0 if args and args[0] in ("-h", "--help") else 2

    if args[0] in ("collect", "render"):
        want = 3 if args[0] == "collect" else 2
        if len(args) != want or not _TOKEN.fullmatch(args[1]):
            print(f"error: bad arguments for {args[0]}: {args[1:]!r}", file=sys.stderr)
            return 2
        return _collect(args[1], args[2]) if args[0] == "collect" else _render(args[1])

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
