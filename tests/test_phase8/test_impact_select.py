"""Phase 8 Task 4 — host-side impact selection (shared/impact_select.py).
No network: Jev is FakeJev passed through shared.jev.ask(client=...)."""
from __future__ import annotations

import json
from dataclasses import replace

from shared.impact_select import QUESTION, Config, decide, load_config
from tests.test_phase8.helpers import FakeJev


def doc(n, size=1000, diff="diff --git a/x.py b/x.py\n+x\n"):
    return {"diff": diff, "changed_chars": 100, "candidates": [
        {"id": f"c{i}", "size": size,
         "facts": {"same_file_as_change": False, "imported_by_changed_file": False, "is_test": False},
         "summary": {"role": "callee", "file": f"r{i}.py", "line": 1, "symbol": "match",
                     "line_text": "def match(command):"}}
        for i in range(n)]}


CFG = Config(mode="jev", keep=0.5, mention=0.2, budget=12000, max_signatures=20,
             context_max=60000, timeout=10)


def test_small_case_skips_jev():
    jev = FakeJev()
    d, log = decide(doc(5), CFG, client=jev)
    assert d == {"tiers": None, "note": "", "drop_changed": False}
    assert log["path"] == "small" and jev.calls == []


def test_jev_path_tiers_and_note():
    d, log = decide(doc(40), CFG, client=FakeJev({"c3": 0.9, "c7": 0.3}))
    assert d["tiers"]["c3"] == "full" and d["tiers"]["c7"] == "signature"
    assert d["tiers"]["c0"] == "counted"
    assert "judged unrelated" in d["note"] and log["path"] == "jev"
    assert log["tiers"] == {"full": 1, "signature": 1, "counted": 38}


def test_question_copy_and_state_shape():
    jev = FakeJev()
    decide(doc(40), CFG, client=jev)
    state, questions = jev.calls[0]
    assert set(state) == {"diff", "candidates"}
    assert state["candidates"]["c0"]["symbol"] == "match"
    assert questions["c0"] == {"type": "noul", "instructions": QUESTION.format(cid="c0")}


def test_batches_respect_size_limit():
    jev = FakeJev()
    decide(doc(600, diff="+" * 30000), CFG, client=jev)
    assert len(jev.calls) > 1
    assert all(len(json.dumps(s)) + len(json.dumps(q)) <= 72000 for s, q in jev.calls)
    assert sum(len(q) for _, q in jev.calls) == 600
    assert all(len(s["diff"]) == 24000 for s, _ in jev.calls)


def test_jev_error_falls_back_to_cap_order():
    d, log = decide(doc(40), CFG, client=FakeJev(error=RuntimeError("down")))
    assert log["path"] == "fallback" and "down" in log["reason"]
    assert "not ranked for relevance" in d["note"]
    assert list(d["tiers"].values()).count("full") == 12


def test_malformed_answers_count_as_unscored():
    jev = FakeJev({"c1": float("nan"), "c2": 0.9, "c4": 1.7}, drop={"c0"})
    d, log = decide(doc(40), CFG, client=jev)
    assert d["tiers"]["c2"] == "full"
    for cid in ("c0", "c1", "c4"):
        assert d["tiers"][cid] == "signature"
    assert log["path"] == "jev"


def test_deadline_bounds_the_wait():
    cfg = replace(CFG, timeout=0.5)
    d, log = decide(doc(600, diff="+" * 24000), cfg, client=FakeJev(delay=2.0))
    assert log["path"] == "fallback" and log["jev_ms"] < 1500


def test_cap_mode_never_calls_jev():
    jev = FakeJev()
    d, log = decide(doc(40), replace(CFG, mode="cap"), client=jev)
    assert jev.calls == [] and log["path"] == "fallback" and log["reason"] == "cap mode"


def test_no_key_falls_back(monkeypatch):
    d, log = decide(doc(40), CFG)
    assert log["path"] == "fallback" and log["reason"] == "no TYPESAFE_API_KEY"


def test_mode_defaults(monkeypatch):
    monkeypatch.delenv("IMPACT_SELECT", raising=False)
    assert load_config().mode == "cap"
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    assert load_config().mode == "jev"
    monkeypatch.setenv("IMPACT_SELECT", "bogus")
    assert load_config().mode == "cap"
    monkeypatch.setenv("IMPACT_SELECT", "OFF")
    assert load_config().mode == "off"


def test_config_defaults(monkeypatch):
    for k in ("IMPACT_KEEP", "IMPACT_MENTION", "IMPACT_MAX_CHARS", "IMPACT_MAX_SIGNATURES",
              "CONTEXT_MAX_CHARS", "IMPACT_SELECT_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    c = load_config()
    assert (c.keep, c.mention, c.budget, c.max_signatures, c.context_max, c.timeout) == \
           (0.5, 0.2, 12000, 20, 60000, 10.0)


def test_total_guard_drops_changed_section():
    big = doc(5)
    big["changed_chars"] = 70000
    d, _ = decide(big, CFG)
    assert d["drop_changed"] is True
