"""Sanity check: every Fixture's `expected` Findings anchor at a real
location in the materialized repo at head_ref.

CR's PR #19 raised the concern that the 5 Sentry fixtures rely on
hand-maintained `(file, line)` anchors with no guard — if a fixture
gets refreshed/rebased or a vendored file is restructured, the
expected anchors silently drift and the matcher starts comparing
against ghost coordinates.

This test materializes every fixture in `ALL_FIXTURES` (forcing the
LocalRepo backend so the suite runs fast and free, regardless of
SANDBOX_BACKEND env), then for each `Finding` asserts:

  1. `Finding.file` exists in the materialized repo at HEAD.
  2. The file has at least `Finding.line` lines (so `:line` isn't
     past EOF).

Both checks are necessary conditions for the matcher's `(file,
category, line ±N)` heuristic to even be meaningful. They are NOT
sufficient — the matcher also needs the fixture's category to match
the planted bug's actual category, but that's a methodological
question rather than a refactor-safety one.

Runtime: ~20s for all 7 fixtures (7 × ~3s for v1+v2 git workflow).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Project root on path so `shared.*` and `sandbox.*` resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.fixtures import ALL_FIXTURES, materialize


@pytest.fixture(autouse=True)
def _force_local_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anchor checks should not provision a Daytona sandbox per fixture
    just to test path validity. Force LocalRepo regardless of what
    SANDBOX_BACKEND is set in the dev's environment.
    """
    monkeypatch.setenv("SANDBOX_BACKEND", "local")


@pytest.mark.parametrize(
    "fixture",
    ALL_FIXTURES,
    ids=[fx.name for fx in ALL_FIXTURES],
)
def test_fixture_expected_anchors_resolve(fixture) -> None:
    """Every expected Finding points at a real file and a real line."""
    with materialize(fixture) as mfx:
        for i, finding in enumerate(fixture.expected):
            ls = mfx.repo.exec(
                f"test -f {finding.file!r} && wc -l < {finding.file!r}"
            )
            assert ls.ok, (
                f"{fixture.name} expected[{i}].file={finding.file!r} "
                f"missing in materialized repo at {mfx.head_ref}: "
                f"exit={ls.exit_code} stderr={ls.stderr!r}"
            )
            try:
                line_count = int(ls.stdout.strip())
            except ValueError:
                pytest.fail(
                    f"{fixture.name} expected[{i}]: could not parse line "
                    f"count from {ls.stdout!r}"
                )
            assert finding.line <= line_count, (
                f"{fixture.name} expected[{i}].line={finding.line} is past "
                f"EOF (file has {line_count} lines): {finding.file!r}"
            )
            assert finding.line >= 1, (
                f"{fixture.name} expected[{i}].line={finding.line} must be "
                f"1-indexed (>= 1)"
            )
