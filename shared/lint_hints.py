"""Linter hints for the review context, filtered by Jev (Phase 10, opt-in).

ruff and pylint run on the changed Python files at head_ref (bug-type rules
only, no style). Warnings on lines the change added are kept; Jev then
answers two yes/no questions per warning, with the diff and, when
available, the machine PR summary (shared/pr_summary.py) in its state:

  mistake    does it point to a likely mistake a reviewer should check?
  on_intent  does it concern the behavior this change adds or modifies?

A warning is shown when mistake >= LINT_HINTS_MISTAKE (0.5) and
on_intent >= LINT_HINTS_INTENT (0.45); the two are separate checks, not
an average. Shown warnings go in a short section before the diff, framed
as hints to verify. Measured offline on BugsInPy (bench/linter-signal):
158 warnings on added lines -> 11-13 shown, keeping all 5 that point at
a fixed bug.

Off unless REVIEW_LINT_HINTS is 1/true/yes/on. Fail-open: missing linters
(e.g. a sandbox without ruff), a Jev error or timeout, or nothing kept
all mean no section. Linters run inside the repo's sandbox (repo.exec);
Jev runs on the host. Not in _HOST_SHARED_FILES.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
from typing import Any

from shared import jev

log = logging.getLogger("shared.lint_hints")

RUFF = "python -m ruff"
PYLINT = "python -m pylint"
RUFF_SELECT = "F,B,E9,PLE,PLW"
PYLINT_ENABLE = ("E,W0101,W0102,W0104,W0106,W0120,W0143,W0199,W0612,W0611,"
                 "W0621,W0631,W0640,W1114")
PYLINT_DISABLE = "E0401,E0611,E0001,E0402"  # import resolution needs the project's dependencies
MAX_WARNINGS = 40
MAX_DIFF_CHARS = 24_000
JEV_TIMEOUT_S = 20.0
HEADER = "## 0b. Linter hints (warnings on lines this change added, filtered by Jev; may be false alarms, verify before reporting)"

QUESTIONS = {
    "mistake": (
        "Linter warning `warnings.{wid}` was reported on a line that this change added (see `diff`). "
        "Does the warning point to a likely mistake in the change, such as wrong behavior, a crash, or a "
        "name that is unused or undefined because something was forgotten, rather than style or harmless "
        "code, so that a code reviewer should check it?"),
    "on_intent": (
        "Does linter warning `warnings.{wid}` concern the behavior that this change adds or modifies (see "
        "`diff`), rather than code the change only moved, renamed, reformatted or left as it was?"),
}


def enabled() -> bool:
    return os.environ.get("REVIEW_LINT_HINTS", "").strip().lower() in {"1", "true", "yes", "on"}


def _threshold(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _added_lines(diff0: str) -> dict[str, set[int]]:
    """file -> added line numbers, from a --unified=0 diff (Python files only)."""
    out: dict[str, set[int]] = {}
    cur = None
    for line in diff0.splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") and line.endswith(".py") else None
            continue
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if m and cur:
            start, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            if n:
                out.setdefault(cur, set()).update(range(start, start + n))
    return out


def _json_array(text: str) -> list:
    """The JSON array in a linter's output; sandboxes may mix in stderr."""
    i = text.find("[")
    if i < 0:
        return []
    try:
        val = json.loads(text[i:])
    except ValueError:
        j = text.rfind("]")
        val = json.loads(text[i:j + 1]) if j > i else []
    return val if isinstance(val, list) else []


def _lint(repo: Any, files: list[str]) -> list[dict]:
    quoted = " ".join(shlex.quote(f) for f in files)
    found: list[dict] = []
    r = repo.exec(f"{RUFF} check --no-cache --isolated --select {RUFF_SELECT} --output-format json "
                  f"--exit-zero {quoted}", timeout=120)
    if "No module named" in (r.stdout + r.stderr):
        raise RuntimeError("ruff is not installed in the sandbox")
    for i in _json_array(r.stdout):
        path = i.get("filename", "")
        rel = next((f for f in files if path.endswith(f)), path)
        found.append({"tool": "ruff", "code": i.get("code") or "E999", "message": i.get("message", ""),
                      "file": rel, "line": i.get("location", {}).get("row", 0)})
    r = repo.exec(f"{PYLINT} --disable=all --enable={PYLINT_ENABLE} --disable={PYLINT_DISABLE} "
                  f"--output-format=json --score=n --persistent=n {quoted}", timeout=240)
    if "No module named" not in (r.stdout + r.stderr):
        for i in _json_array(r.stdout):
            found.append({"tool": "pylint", "code": i.get("message-id", ""),
                          "message": f"{i.get('symbol', '')}: {i.get('message', '')}",
                          "file": i.get("path", ""), "line": i.get("line", 0)})
    return found


def collect(repo: Any, base_ref: str, head_ref: str) -> dict:
    """Run the linters and keep warnings on added lines. Raises on failure."""
    rng = f"{shlex.quote(base_ref)}..{shlex.quote(head_ref)}"
    r0 = repo.exec(f"git diff --unified=0 --no-color {rng}", timeout=60)
    r3 = repo.exec(f"git diff --unified=3 --no-color {rng}", timeout=60)
    if not (r0.ok and r3.ok):
        raise RuntimeError("git diff failed")
    added = _added_lines(r0.stdout)
    warnings: list[dict] = []
    if added:
        files = sorted(added)
        seen = set()
        for w in _lint(repo, files):
            if w["line"] not in added.get(w["file"], ()):
                continue
            key = (w["tool"], w["code"], w["file"], w["line"])
            if key in seen:
                continue
            seen.add(key)
            warnings.append(w)
        texts: dict[str, list[str]] = {}
        for w in warnings:
            if w["file"] not in texts:
                rr = repo.exec(f"git show {shlex.quote(head_ref)}:{shlex.quote(w['file'])}", timeout=30)
                texts[w["file"]] = rr.stdout.splitlines() if rr.ok else []
            lines = texts[w["file"]]
            w["line_text"] = lines[w["line"] - 1].strip()[:200] if 0 < w["line"] <= len(lines) else ""
        warnings = warnings[:MAX_WARNINGS]
        for i, w in enumerate(warnings):
            w["id"] = f"w{i}"
    return {"diff": r3.stdout, "warnings": warnings}


def select(collected: dict, *, summary: dict | None = None, client: Any = None) -> list[dict]:
    """Warnings that pass both checks. Raises if Jev fails."""
    ws = collected["warnings"]
    if not ws:
        return []
    state: dict[str, Any] = {"diff": collected["diff"][:MAX_DIFF_CHARS]}
    if summary:
        state["pr_summary"] = {
            "source": "machine summary written by Haiku from the diff; may be wrong",
            **{k: summary.get(k, [] if k != "what_changed" else "") for k in (
                "what_changed", "behavior_before_after", "interfaces_touched", "data_touched",
                "error_handling_changes")}}
    state["warnings"] = {w["id"]: {k: w[k] for k in ("tool", "code", "message", "file", "line", "line_text")}
                         for w in ws}
    questions = {f"{q}__{w['id']}": {"type": "noul", "instructions": t.format(wid=w["id"])}
                 for q, t in QUESTIONS.items() for w in ws}
    resp = jev.ask(state, questions, timeout=JEV_TIMEOUT_S, client=client)
    nouls = getattr(resp, "nouls", {}) or {}

    def p(key: str) -> float:
        v = getattr(nouls.get(key), "noul", None)
        return float(v) if isinstance(v, (int, float)) else 0.0

    keep_m, keep_i = _threshold("LINT_HINTS_MISTAKE", 0.5), _threshold("LINT_HINTS_INTENT", 0.45)
    kept = []
    for w in ws:
        m, i = p(f"mistake__{w['id']}"), p(f"on_intent__{w['id']}")
        if m >= keep_m and i >= keep_i:
            kept.append({**w, "mistake": round(m, 3), "on_intent": round(i, 3)})
    return kept


def for_repo(repo: Any, base_ref: str, head_ref: str, *, summary: dict | None = None,
             client: Any = None) -> list[dict] | None:
    """Collect and select; None on any failure. Never raises."""
    try:
        return select(collect(repo, base_ref, head_ref), summary=summary, client=client)
    except Exception as e:  # noqa: BLE001 — hints must never fail the review
        log.warning("lint_hints: no hints (%s: %s)", type(e).__name__, e)
        return None


def render(kept: list[dict]) -> str:
    rows = [f"{w['file']}:{w['line']}  {w['code']}  {w['message']}" for w in kept]
    body = "\n".join(rows).replace("<", "&lt;")
    return f"{HEADER}\n\n<lint_hints>\n{body}\n</lint_hints>\n\n"


def insert(context: str, kept: list[dict]) -> str:
    """Put the section right before the diff (after the PR summary, if any)."""
    if not kept:
        return context
    section = render(kept)
    i = context.find("## 1. Git Diff")
    if i >= 0:
        return context[:i] + section + context[i:]
    # No diff heading (e.g. ODIS returned an error): after the summary, else first.
    j = context.find("</pr_summary>\n")
    if j >= 0:
        j += len("</pr_summary>\n")
        return context[:j] + "\n" + section + context[j:].lstrip("\n")
    return section + context


def trace_lines(kept: list[dict] | None) -> list[str]:
    if kept is None:
        return ["--- Linter hints (REVIEW_LINT_HINTS): unavailable, review proceeds without them ---"]
    if not kept:
        return ["--- Linter hints (REVIEW_LINT_HINTS): none passed the Jev filter ---"]
    return ["--- Linter hints (REVIEW_LINT_HINTS, shown before the diff) ---"] + [
        f"{w['file']}:{w['line']}  {w['code']}  {w['message']}  (mistake {w.get('mistake')}, on_intent {w.get('on_intent')})"
        for w in kept]
