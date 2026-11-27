"""Phase 8 Task 1 — ODIS split into collect + render, byte-identical.

The goldens in golden/ were recorded from the unmodified
`build_context` before the split (2026-11-26).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from shared import odis
from shared.fixtures import ALL_FIXTURES, CONTRACT_MISMATCH, materialize

GOLDEN = Path(__file__).parent / "golden"


@pytest.mark.parametrize("fx", ALL_FIXTURES, ids=lambda f: f.name)
def test_build_context_matches_golden(fx):
    with materialize(fx) as m:
        out = odis.build_context(m.repo.path, m.base_ref, m.head_ref)
    assert out == (GOLDEN / f"{fx.name}.md").read_text()


@pytest.mark.parametrize("fx", ALL_FIXTURES, ids=lambda f: f.name)
def test_collect_then_render_matches_golden(fx):
    with materialize(fx) as m:
        c = odis.collect(m.repo.path, m.base_ref, m.head_ref)
    assert odis.render_markdown(c) == (GOLDEN / f"{fx.name}.md").read_text()
    assert [x.id for x in c.candidates] == [f"c{i}" for i in range(len(c.candidates))]


def test_candidate_facts_on_contract_mismatch():
    with materialize(CONTRACT_MISMATCH) as m:
        c = odis.collect(m.repo.path, m.base_ref, m.head_ref)
    caller = next(x for x in c.candidates if x.role == "caller")
    assert caller.line_text == "x = add(1, 2)"
    assert caller.inside_function == "report"
    assert caller.is_test is False
    assert caller.imported_by_changed_file is False
    assert all(x.text for x in c.candidates)


def test_callee_facts_on_sentry_fixture():
    fx = next(f for f in ALL_FIXTURES if f.name == "sentry_80168")
    with materialize(fx) as m:
        c = odis.collect(m.repo.path, m.base_ref, m.head_ref)
    callees = [x for x in c.candidates if x.role == "callee"]
    assert callees
    assert all(x.line_text.startswith(("def ", "async def ", "class ")) for x in callees)
