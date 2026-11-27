"""verify_reviews: the Jev questions about a finished review, and the state they see."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bugsinpy_bench" / "scripts"))

from verify_reviews import QUESTIONS, review_state, verify  # noqa: E402

REVIEW = {
    "findings": [{"file": "a.py", "line": 3, "line_end": 4, "category": "logic", "severity": "high",
                  "summary": "s" * 500, "detail": "d" * 2000, "suggested_fix": "f"}],
    "closing_message": "c" * 9000,
}
FILES = [{"path": "a.py", "added": 2, "removed": 1}]


class FakeJev:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def system_one(self, state, questions):
        self.calls.append((state, questions))
        if self.error:
            raise self.error
        return SimpleNamespace(answers={n: SimpleNamespace(type="noul", noul=0.25) for n in questions},
                               usage=SimpleNamespace(input_tokens=900, output_tokens=30))


def test_questions_are_the_three_from_the_design():
    assert list(QUESTIONS) == ["unfiled_issue", "dismissed_as_intended", "could_not_verify"]
    assert all(q["type"] == "noul" and "`closing_message`" in q["instructions"] for q in QUESTIONS.values())


def test_state_holds_only_the_declared_fields_and_cuts_long_text():
    s = review_state("title", FILES, REVIEW)
    assert list(s) == ["pull_request_title", "files_changed", "findings", "closing_message"]
    assert s["files_changed"] == FILES
    assert list(s["findings"][0]) == ["file", "line", "severity", "category", "summary"]
    assert len(s["findings"][0]["summary"]) == 300
    assert len(s["closing_message"]) == 6000


def test_verify_returns_the_three_probabilities_and_usage():
    jev = FakeJev()
    out = verify(review_state("t", FILES, REVIEW), jev)
    assert out == {"answers": {"unfiled_issue": 0.25, "dismissed_as_intended": 0.25, "could_not_verify": 0.25},
                   "usage": {"input_tokens": 900, "output_tokens": 30}}
    assert len(jev.calls) == 1


def test_a_jev_error_is_recorded_by_class_name_only():
    assert verify(review_state("t", FILES, REVIEW), FakeJev(error=TimeoutError("secret body"))) == {"error": "TimeoutError"}
