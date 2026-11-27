"""review_digest: read a stored review back out of its result file and trace."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bugsinpy_bench" / "scripts"))

from agent_sdk.reviewer import _draw_box  # noqa: E402  (the real trace writer)
from review_digest import closing_message, load_reviews, parse_result_file  # noqa: E402

SUBMIT = "mcp__reviewer__submit_findings"


def _assistant(blocks):
    """Buffer lines as agent_sdk.reviewer._append_assistant_blocks builds them."""
    lines = ["usage: in=1 cache_w=0 cache_r=0 out=1"]
    for kind, value in blocks:
        lines.append("")
        if kind == "text":
            lines.append("text:")
            lines += [f"  {t}" for t in (value.splitlines() or [""])]
        else:
            lines.append(f"tool_use: {value}")
            lines.append('  args: {"findings": []}')
    return lines


def _trace(turns):
    out: list[str] = []
    for i, (kind, lines) in enumerate(turns, start=1):
        _draw_box(out.append, f"TURN {i:02d}  [{kind}]", lines)
    return "\n".join(out) + "\n"


LONG = "This sentence is much longer than the seventy-six characters a trace line holds, " * 3
CLOSING = f"I found one bug.\n\n- **High:** {LONG}\n  indented detail line\n\nNot reported: a naming nit."


def test_closing_message_round_trips_wrapped_text():
    trace = _trace([
        ("INIT", ["model: x"]),
        ("assistant", _assistant([("text", "Let me read the diff first."), ("tool_use", "mcp__reviewer__bash")])),
        ("tool_result", ["for: mcp__reviewer__bash", "", "preview:", "  ok"]),
        ("assistant", _assistant([("text", "Submitting one finding."), ("tool_use", SUBMIT)])),
        ("tool_result", [f"for: {SUBMIT}", "", "preview:", "  ok"]),
        ("assistant", _assistant([("text", CLOSING)])),
        ("RESULT", ["stop_reason: end_turn"]),
    ])
    assert closing_message(trace) == "Submitting one finding.\n\n" + CLOSING


def test_text_before_the_submit_turn_is_left_out():
    trace = _trace([
        ("assistant", _assistant([("text", "Early note about the diff."), ("tool_use", "mcp__reviewer__grep")])),
        ("assistant", _assistant([("tool_use", SUBMIT)])),
        ("assistant", _assistant([("text", "Done.")])),
    ])
    assert closing_message(trace) == "Done."


def test_a_full_width_line_is_not_joined_with_the_next_line():
    full = "x" * 74  # two-space indent + 74 characters fills a 76-character trace line
    trace = _trace([("assistant", _assistant([("tool_use", SUBMIT)])),
                    ("assistant", _assistant([("text", f"{full}\nnext line")]))])
    assert closing_message(trace) == f"{full}\nnext line"


def test_a_review_that_never_submitted_uses_its_last_turn():
    trace = _trace([("assistant", _assistant([("text", "First."), ("tool_use", "mcp__reviewer__bash")])),
                    ("assistant", _assistant([("text", "Ran out of turns.")])),
                    ("RESULT", ["stop_reason: max_turns"])])
    assert closing_message(trace) == "Ran out of turns."
    assert closing_message("") == ""


def test_parse_result_file_reads_header_and_findings():
    path = (ROOT / "bugsinpy_bench" / "results" / "sweep_2026-11-26_haiku55_medium_pilot30"
            / "runs" / "agent_medium_PySnooper_3.txt")
    r = parse_result_file(path.read_text())
    assert (r["label"], r["run_id"], r["num_turns"], r["exit_reason"]) == ("PySnooper#3", 419, 6, "submit_findings")
    assert len(r["findings"]) == 2 and {"file", "line", "severity", "summary"} <= set(r["findings"][0])


def test_load_reviews_covers_all_100_bugs_for_each_model():
    for arm in ("haiku", "sonnet", "opus"):
        reviews = load_reviews(arm)
        assert len(reviews) == 100
        assert all(isinstance(r["closing_message"], str) and isinstance(r["findings"], list) for r in reviews.values())
    # This review submitted twice (the first attempt failed validation), so its
    # closing message starts at the second submit turn and then gives the summary.
    closing = load_reviews("haiku")["PySnooper#3"]["closing_message"]
    assert closing.startswith("The submission failed validation")
    assert "I submitted two findings for this commit." in closing
    assert "file output is broken (`pysnooper/pysnooper.py:34`)" in closing
