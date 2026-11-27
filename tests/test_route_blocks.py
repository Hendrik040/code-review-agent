import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bugsinpy_bench" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from route_blocks import BLOCK_QUESTIONS, PR_QUESTIONS, block_state, route_entry  # noqa: E402
from test_block_summaries import TWO_FILE_DIFF, FakeClient as FakeHaiku  # noqa: E402


class FakeJev:
    def __init__(self, fail_blocks=False):
        self.fail_blocks = fail_blocks
        self.calls = 0

    def system_one(self, state, questions):
        self.calls += 1
        if self.fail_blocks and "block" in state:
            raise TimeoutError("boom")
        answers = {}
        for name, q in questions.items():
            if q["type"] == "noul":
                answers[name] = SimpleNamespace(type="noul", noul=0.2)
            else:
                n = len(q["criteria"])
                answers[name] = SimpleNamespace(type="score", probabilities={i: 1.0 / n for i in range(n)})
        return SimpleNamespace(answers=answers, usage=SimpleNamespace(input_tokens=10, output_tokens=1))


def test_arm_A_hides_complexity_arm_B_shows_it():
    b = {"block_id": "f::g::0", "complexity_1_10": 7, "before": "x", "after": "y"}
    assert "complexity_1_10" not in block_state("t", b, "A")["block"]
    assert block_state("t", b, "B")["block"]["complexity_1_10"] == 7


def test_question_ids_are_the_eleven_from_the_spec():
    assert list(BLOCK_QUESTIONS) == ["precision_logic", "state_tracking", "error_path",
                                     "contract_change", "value_domain", "async_flow", "verify_effort"]
    assert list(PR_QUESTIONS) == ["change_kind", "beyond_title", "tests_exercise_change", "high_stakes"]


def test_one_jev_call_per_block_plus_one_per_pr(tmp_path):
    jev = FakeJev()
    e = route_entry("x#1", "t", TWO_FILE_DIFF, "A", jev_client=jev,
                    haiku_client=FakeHaiku(blocks_per_call=2), cache_dir=tmp_path)
    assert e["jev_calls"] == 5 and len(e["blocks"]) == 4
    assert len(e["pr"]["change_kind"]) == 4


def test_block_error_is_recorded_not_raised(tmp_path):
    e = route_entry("x#1", "t", TWO_FILE_DIFF, "A", jev_client=FakeJev(fail_blocks=True),
                    haiku_client=FakeHaiku(blocks_per_call=1), cache_dir=tmp_path)
    assert all(b.get("error") == "TimeoutError" for b in e["blocks"]) and e["pr"]["error"] is None


def test_pr_state_lists_only_described_files(tmp_path):
    diff = "".join(
        f"diff --git a/f{i}.py b/f{i}.py\n--- a/f{i}.py\n+++ b/f{i}.py\n@@ -1 +1,{i + 1} @@\n-x\n"
        + "".join(f"+y{j}\n" for j in range(i + 1))
        for i in range(45)
    )
    seen = []

    class Spy(FakeJev):
        def system_one(self, state, questions):
            if "files_changed" in state:
                seen.append(state)
            return super().system_one(state, questions)

    e = route_entry("x#1", "t", diff, "A", jev_client=Spy(),
                    haiku_client=FakeHaiku(blocks_per_call=1), cache_dir=tmp_path)
    (st,) = seen
    assert len(st["files_changed"]) == 40 and st["files_dropped"] == 5
    assert e["files_dropped"] == 5
