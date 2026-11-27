"""Phase 8 Task 2 — tier assignment, fallback order, note (shared/impact.py)."""
from __future__ import annotations

from types import SimpleNamespace

from shared import impact


def C(i, role="callee", file="a.py", symbol="f", same=False, imp=False, test=False):
    return SimpleNamespace(
        id=f"c{i}", role=role, file=file, line=i + 1, symbol=symbol,
        line_text=f"def {symbol}():", doc="", inside_function="",
        same_file_as_change=same, imported_by_changed_file=imp, is_test=test,
    )


def test_scores_map_to_tiers_at_thresholds():
    cs = [C(0), C(1), C(2), C(3)]
    t = impact.assign_tiers(cs, {c.id: 10 for c in cs},
                            {"c0": 0.5, "c1": 0.49, "c2": 0.2, "c3": 0.19},
                            keep=0.5, mention=0.2, budget=1000, max_signatures=20)
    assert t == {"c0": "full", "c1": "signature", "c2": "signature", "c3": "counted"}


def test_budget_demotes_lowest_full_and_skips_oversize():
    cs = [C(0), C(1), C(2)]
    t = impact.assign_tiers(cs, {"c0": 600, "c1": 900, "c2": 300},
                            {"c0": 0.9, "c1": 0.8, "c2": 0.7},
                            keep=0.5, mention=0.2, budget=1000, max_signatures=20)
    assert t == {"c0": "full", "c1": "signature", "c2": "full"}


def test_signature_cap_overflow_is_counted():
    cs = [C(i) for i in range(25)]
    t = impact.assign_tiers(cs, {c.id: 10 for c in cs}, {c.id: 0.3 for c in cs},
                            keep=0.5, mention=0.2, budget=1000, max_signatures=20)
    assert list(t.values()).count("signature") == 20
    assert list(t.values()).count("counted") == 5


def test_fallback_order_fills_budget_then_signatures():
    cs = [C(0, file="z.py"), C(1, file="b.py", imp=True), C(2, file="a.py", same=True),
          C(3, file="t.py", test=True, imp=True)]
    t = impact.assign_tiers(cs, {c.id: 400 for c in cs}, None,
                            keep=0.5, mention=0.2, budget=800, max_signatures=1)
    assert t == {"c2": "full", "c1": "full", "c3": "signature", "c0": "counted"}


def test_partial_scores_put_unscored_after_scored():
    cs = [C(0), C(1, same=True)]
    t = impact.assign_tiers(cs, {"c0": 10, "c1": 10}, {"c0": 0.9},
                            keep=0.5, mention=0.2, budget=1000, max_signatures=20)
    assert t == {"c0": "full", "c1": "signature"}


def test_dedupe_keeps_first():
    a, b = C(0), C(0)
    b.id = "c1"
    assert [x.id for x in impact.dedupe([a, b])] == ["c0"]


def test_note_wording_ranked_and_unranked():
    cs = [C(0, symbol="match"), C(1, symbol="match"), C(2, role="caller", symbol="match")]
    tiers = {"c0": "full", "c1": "counted", "c2": "counted"}
    assert impact.not_shown_note(cs, tiers, ranked=True) == (
        "Not shown: 1 other definition of `match` and 1 other call site, judged unrelated "
        "to this change. Use grep or read_file_section if you need one.")
    assert "not ranked for relevance" in impact.not_shown_note(cs, tiers, ranked=False)
    assert impact.not_shown_note(cs, {k: "full" for k in tiers}, ranked=True) == ""


def test_note_lists_at_most_five_names_and_pluralises():
    cs = [C(i, symbol=f"s{i}") for i in range(7)]
    note = impact.not_shown_note(cs, {c.id: "counted" for c in cs}, ranked=True)
    assert note.startswith("Not shown: 7 other definitions of `s0`, `s1`, `s2`, `s3`, `s4`, …, judged")


def test_caller_symbol_prefix_is_stripped_in_note():
    cs = [C(0, role="caller", symbol="call to add")]
    note = impact.not_shown_note(cs, {"c0": "counted"}, ranked=True)
    assert note.startswith("Not shown: 1 other call site, judged")


def test_summary_shape():
    c = C(0)
    c.doc = "Does f."
    assert impact.summary(c) == {"role": "callee", "file": "a.py", "line": 1, "symbol": "f",
                                 "line_text": "def f():", "docstring_first_line": "Does f."}


def test_signature_line_names_the_symbol_for_callers():
    a = SimpleNamespace(role="caller", file="r.py", line=10, symbol="call to match",
                        line_text="return match('x') and get_new_command('x')")
    b = SimpleNamespace(role="caller", file="r.py", line=10, symbol="call to get_new_command",
                        line_text=a.line_text)
    assert impact.signature_line(a) != impact.signature_line(b)
    assert impact.signature_line(a).startswith("r.py:10  [match]  return")
