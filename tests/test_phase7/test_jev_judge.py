"""Phase 7 — Jev as the Learnings-layer judge (learnings/jev_judge.py).

No network: `shared.jev.ask` is stubbed with the shape typesafe-sdk
returns (`.nouls[name].noul`).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from learnings import capture, jev_judge
from learnings.extractor import Extractor
from learnings.qdrant_store import Hit
from shared import jev
from shared.learnings import applicability_filter

DIFF = "diff --git a/a.py b/a.py\n+++ b/a.py\n@@ -1 +1 @@\n+x = retry(3)\n"


def _hit(i: int, file_path: str = "a.py") -> Hit:
    return Hit(point_id=str(i), score=0.9 - i / 100, payload={
        "learning_text": f"lesson {i}", "file_path": file_path,
        "line_start": 1, "line_end": 2, "code_chunk_text": "x = retry(1)",
    })


@pytest.fixture
def jev_says(monkeypatch):
    """Turn Jev on and script its P(yes) answers, in call order."""
    def install(*answers):
        calls: list[dict] = []
        queue = list(answers)

        def fake_ask(state, questions, *, timeout=10.0, client=None):
            calls.append({"state": state, "questions": questions})
            answer = queue.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return SimpleNamespace(nouls={"q": SimpleNamespace(noul=answer)})

        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr(jev, "ask", fake_ask)
        return calls
    return install


def _haiku(word: str) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(content=[SimpleNamespace(text=word)])
    return client


def test_off_without_a_key_and_with_the_haiku_switch(monkeypatch):
    assert jev_judge.enabled() is False
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    assert jev_judge.enabled() is True
    monkeypatch.setenv("LEARNINGS_JUDGE", "haiku")
    assert jev_judge.enabled() is False


def test_jev_judges_applicability_and_haiku_is_not_called(jev_says):
    calls = jev_says(0.9, 0.1, 0.45)  # yes, no, maybe
    haiku = _haiku("no")
    out = applicability_filter([_hit(0), _hit(1), _hit(2)],
                               anthropic_client=haiku, diff_summary=DIFF)
    assert [h.point_id for h in out] == ["0", "2"]
    haiku.messages.create.assert_not_called()
    assert "lesson 0" in calls[0]["state"] and "retry(3)" in calls[0]["state"]
    assert calls[0]["questions"]["q"]["type"] == "noul"


def test_drop_line_is_configurable(jev_says, monkeypatch):
    jev_says(0.2)
    monkeypatch.setenv("LEARNINGS_JEV_DROP_BELOW", "0.1")
    out = applicability_filter([_hit(0)], anthropic_client=_haiku("no"), diff_summary=DIFF)
    assert len(out) == 1


def test_hit_whose_file_is_not_in_the_diff_is_kept_without_a_call(jev_says):
    calls = jev_says()
    out = applicability_filter([_hit(0, "other.py")],
                               anthropic_client=_haiku("no"), diff_summary=DIFF)
    assert len(out) == 1 and calls == []


def test_jev_failure_hands_the_whole_pass_to_haiku(jev_says):
    jev_says(0.9, RuntimeError("boom"))
    haiku = _haiku("no")
    out = applicability_filter([_hit(0), _hit(1)], anthropic_client=haiku, diff_summary=DIFF)
    assert out == []                      # Haiku said no to both
    assert haiku.messages.create.call_count == 2


def test_without_a_key_the_haiku_path_is_unchanged():
    haiku = _haiku("yes")
    out = applicability_filter([_hit(0)], anthropic_client=haiku, diff_summary=DIFF)
    assert len(out) == 1 and haiku.messages.create.call_count == 1


EX = Extractor(handle="@Working-Ant", call_words=("learn", "remember"))


def test_capture_stores_the_maintainers_paragraph_when_jev_says_learning(jev_says):
    jev_says(0.93)
    body = "Good catch, but @Working-Ant in this codebase\nthat pattern is intentional.\n\nThanks!"
    m = capture._extract_mention(EX, body, anthropic_client=None)
    assert m is not None and m.call_word == "(jev)"
    assert m.text == "Good catch, but in this codebase that pattern is intentional."


def test_capture_skips_haiku_when_jev_says_not_a_learning(jev_says):
    jev_says(0.04)
    haiku = MagicMock()
    assert capture._extract_mention(EX, "@Working-Ant thanks!", anthropic_client=haiku) is None
    haiku.messages.create.assert_not_called()


def test_capture_falls_back_to_haiku_when_jev_fails(jev_says):
    jev_says(TimeoutError("slow"))
    haiku = _haiku('{"is_learning": true, "lesson_text": "Prefer X."}')
    m = capture._extract_mention(EX, "@Working-Ant we prefer X here", anthropic_client=haiku)
    assert m is not None and (m.call_word, m.text) == ("(llm)", "Prefer X.")


def test_call_word_mentions_never_reach_a_classifier(jev_says):
    calls = jev_says()
    m = capture._extract_mention(EX, "@Working-Ant remember: use tz-aware datetimes",
                                 anthropic_client=None)
    assert m is not None and m.call_word == "remember" and calls == []


def test_yes_probability_builds_a_request_the_real_sdk_accepts():
    pytest.importorskip("typesafe_sdk")
    import json

    import httpx2
    from typesafe_sdk import TypeSafeClient

    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json={
            "model": "jev-1", "usage": {"input_tokens": 50, "output_tokens": 1},
            "answers": {"q": {"type": "noul", "noul": 0.81}},
        })

    with TypeSafeClient(api_key="k", compression=False,
                        transport=httpx2.MockTransport(handler)) as client:
        verdict = jev_judge.applicability(_hit(0).payload, DIFF, client=client)
    assert verdict == "yes"
    q = seen["body"]["questions"]["q"]
    assert q["type"] == "noul" and set(q["criteria"]) == {"true", "false"}
