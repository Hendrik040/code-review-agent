"""Read a stored review back: what the reviewer submitted and what it said at the end.

A BugsInPy run leaves two files: the result file under
bugsinpy_bench/results/<sweep>/runs/ (header plus the submitted findings as
JSON) and the trace agent_sdk/traces/run_NNN.txt (every turn, drawn as boxes).
The reviewer's closing message exists only in the trace, hard-wrapped at 76
characters by agent_sdk/reviewer.py::_draw_box; `closing_message` undoes that.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS = ROOT / "bugsinpy_bench" / "results"
TRACES = ROOT / "agent_sdk" / "traces"

ARM_SWEEPS = {
    "haiku": ["sweep_2026-11-26_haiku55_medium_pilot30", "sweep_2026-11-27_haiku55_medium_rest70"],
    "sonnet": ["sweep_2026-11-26_sonnet55_high_pilot30", "sweep_2026-11-27_sonnet55_high_rest70"],
    "opus": ["sweep_2026-11-27_opus55_high_pilot30", "sweep_2026-11-27_opus55_high_rest70"],
}

WIDTH = 76  # _draw_box cuts every line into chunks of exactly this many characters
SUBMIT_SUFFIX = "submit_findings"
_BOX_START = re.compile(r"^┌─ TURN \d+\s+\[(\w+)\]")


def _boxes(trace_text: str) -> list[tuple[str, list[str | None]]]:
    """[(kind, chunks)]. A chunk is the text after "│ "; None is a bare "│",
    which the writer puts between blocks."""
    boxes: list[tuple[str, list[str | None]]] = []
    cur: list[str | None] | None = None
    for line in trace_text.splitlines():
        m = _BOX_START.match(line)
        if m:
            cur = []
            boxes.append((m.group(1), cur))
        elif cur is None:
            continue
        elif line.startswith("└"):
            cur = None
        elif line == "│":
            cur.append(None)
        elif line.startswith("│ "):
            cur.append(line[2:])
    return boxes


def _logical_lines(chunks: list[str | None]) -> list[str | None]:
    """Undo the wrap: a chunk continues the line before it when that chunk was
    full width. Every text line starts with a two-space indent, so a chunk that
    starts with two spaces is taken as a new line even after a full one."""
    out: list[str | None] = []
    prev_full = False
    for c in chunks:
        if c is None:
            out.append(None)
            prev_full = False
            continue
        if prev_full and out and out[-1] is not None and not c.startswith("  "):
            out[-1] += c
        else:
            out.append(c)
        prev_full = len(c) == WIDTH
    return out


def _assistant_blocks(chunks: list[str | None]) -> list[tuple[str, str]]:
    """[("text", text) | ("tool_use", tool name)] in the order they were written."""
    blocks: list[tuple[str, str]] = []
    mode: str | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal mode, buf
        if mode == "text":
            blocks.append(("text", "\n".join(buf)))
        mode, buf = None, []

    for line in _logical_lines(chunks):
        if line is None:
            flush()
        elif mode is None:
            if line == "text:":
                mode = "text"
            elif line.startswith("tool_use: "):
                blocks.append(("tool_use", line[len("tool_use: "):].strip()))
                mode = "tool"
        elif mode == "text":
            buf.append(line[2:] if line.startswith("  ") else line)
    flush()
    return blocks


def closing_message(trace_text: str) -> str:
    """The reviewer's own text from the turn that called submit_findings onward.
    A review that never submitted gives the text of its last turn."""
    turns = [_assistant_blocks(chunks) for kind, chunks in _boxes(trace_text) if kind == "assistant"]
    if not turns:
        return ""
    submits = [i for i, blocks in enumerate(turns)
               if any(k == "tool_use" and v.endswith(SUBMIT_SUFFIX) for k, v in blocks)]
    start = submits[-1] if submits else len(turns) - 1
    texts = [v for blocks in turns[start:] for k, v in blocks if k == "text" and v.strip()]
    return "\n\n".join(texts)


def parse_result_file(text: str) -> dict:
    head, _, body = text.partition("\n# ---\n")

    def field(name: str, cast=str, default=None):
        m = re.search(rf"^# {re.escape(name)}: (.+)$", head, re.M)
        return cast(m.group(1).strip()) if m else default

    run = re.search(r"^# Agent SDK reviewer run (\d+)", head, re.M)
    try:
        findings = json.loads(body) if body.strip() else []
    except json.JSONDecodeError:
        findings = []
    return {
        "label": field("bug"),
        "model": field("model"),
        "run_id": int(run.group(1)) if run else None,
        "num_turns": field("num_turns", int, 0),
        "exit_reason": field("exit_reason", str, ""),
        "cost_usd": field("cost_usd", float, 0.0),
        "findings": findings if isinstance(findings, list) else [],
    }


def load_reviews(arm: str) -> dict[str, dict]:
    """label -> the stored review of one model, with its closing message."""
    out: dict[str, dict] = {}
    for sweep in ARM_SWEEPS[arm]:
        for path in sorted((RESULTS / sweep / "runs").glob("*.txt")):
            r = parse_result_file(path.read_text())
            trace = TRACES / f"run_{r['run_id']:03d}.txt" if r["run_id"] is not None else None
            r["closing_message"] = (
                closing_message(trace.read_text(errors="replace")) if trace and trace.exists() else ""
            )
            out[r["label"]] = r
    return out
