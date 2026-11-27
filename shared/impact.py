"""Tiering for ODIS impact candidates (Phase 8).

Decides, per caller/callee candidate, how much of it the reviewer sees:
"full" (the snippet), "signature" (one line) or "counted" (only a count
in the "not shown" note). Scores come from Jev (shared/impact_select.py)
or are absent, in which case a fixed order is used.

Runs on both sides: the host decides tiers, the sandbox renders them.
So this module imports only the stdlib, and it is listed in
sandbox/daytona.py::_HOST_SHARED_FILES. Candidates are duck-typed: any
object with the ImpactCandidate fields (shared/odis.py) works.
"""

from __future__ import annotations

import re
from typing import Any

FULL, SIGNATURE, COUNTED = "full", "signature", "counted"

_CALL_PREFIX = "call to "
_SIGNATURE_MAX = 200
_NOTE_MAX_NAMES = 5


def _bare_symbol(c: Any) -> str:
    s = c.symbol
    return s[len(_CALL_PREFIX):] if s.startswith(_CALL_PREFIX) else s


def summary(c: Any) -> dict:
    """What Jev sees about one candidate. Extracted by code, never written
    by a model; optional keys appear only when non-empty."""
    out = {
        "role": c.role, "file": c.file, "line": c.line,
        "symbol": c.symbol, "line_text": c.line_text,
    }
    if getattr(c, "doc", ""):
        out["docstring_first_line"] = c.doc
    if getattr(c, "inside_function", ""):
        out["inside_function"] = c.inside_function
    return out


def fallback_key(c: Any) -> tuple:
    """Order used when nothing was scored: same file as the change, then
    files the change imports, then non-test code, then path and line."""
    return (
        not c.same_file_as_change,
        not c.imported_by_changed_file,
        bool(c.is_test),
        c.file,
        c.line,
    )


def dedupe(cands: list) -> list:
    """First occurrence per (role, file, line, symbol). Today's ODIS can
    emit the same snippet twice; the tiered paths show it once."""
    seen: set[tuple] = set()
    out = []
    for c in cands:
        key = (c.role, c.file, c.line, c.symbol)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def assign_tiers(
    cands: list,
    sizes: dict[str, int],
    scores: dict[str, float] | None,
    *,
    keep: float,
    mention: float,
    budget: int,
    max_signatures: int,
) -> dict[str, str]:
    """A tier for every candidate in `cands`.

    With scores: >= keep wants "full", >= mention or unscored wants
    "signature", the rest "counted". Without scores every candidate
    wants "full", in fallback order. Full wishes are granted in order
    while the budget lasts (an oversize one is skipped, not a stopper)
    and the rest become signature candidates; at most `max_signatures`
    signatures are shown, the overflow is counted.
    """
    if scores:
        scored = [c for c in cands if c.id in scores]
        unscored = sorted((c for c in cands if c.id not in scores), key=fallback_key)
        by_score = sorted(scored, key=lambda c: -scores[c.id])
        want_full = [c for c in by_score if scores[c.id] >= keep]
        want_sig = [c for c in by_score if mention <= scores[c.id] < keep] + unscored
    else:
        want_full = sorted(cands, key=fallback_key)
        want_sig = []

    tiers: dict[str, str] = {c.id: COUNTED for c in cands}
    used = 0
    demoted = []
    for c in want_full:
        size = sizes.get(c.id, 0)
        if used + size <= budget:
            tiers[c.id] = FULL
            used += size
        else:
            demoted.append(c)
    for c in (demoted + want_sig)[:max_signatures]:
        tiers[c.id] = SIGNATURE
    return tiers


def _plural(n: int, word: str) -> str:
    return f"{n} other {word}{'' if n == 1 else 's'}"


def not_shown_note(cands: list, tiers: dict[str, str], *, ranked: bool) -> str:
    """One sentence telling the reviewer what was left out, so it can
    fetch it with grep or read_file_section. Empty when nothing was."""
    counted = [c for c in cands if tiers.get(c.id) == COUNTED]
    if not counted:
        return ""
    defs = [c for c in counted if c.role == "callee"]
    calls = [c for c in counted if c.role == "caller"]
    clauses = []
    if defs:
        names: list[str] = []
        for c in defs:
            name = _bare_symbol(c)
            if name not in names:
                names.append(name)
        shown = ", ".join(f"`{n}`" for n in names[:_NOTE_MAX_NAMES])
        if len(names) > _NOTE_MAX_NAMES:
            shown += ", …"
        clauses.append(f"{_plural(len(defs), 'definition')} of {shown}")
    if calls:
        clauses.append(_plural(len(calls), "call site"))
    why = "judged unrelated to this change" if ranked else "not ranked for relevance"
    return (
        f"Not shown: {' and '.join(clauses)}, {why}. "
        "Use grep or read_file_section if you need one."
    )


def signature_line(c: Any) -> str:
    """`file:line  [name]  <source line>` (name for callers only) on one line, at most 200 characters,
    with `<` escaped so repository text cannot close a context tag."""
    text = re.sub(r"\s+", " ", c.line_text or "").strip().replace("<", "&lt;")
    # A caller line can call several changed names; say which one this is.
    tag = f"[{_bare_symbol(c)}]  " if getattr(c, "role", "") == "caller" else ""
    return f"{c.file}:{c.line}  {tag}{text}"[:_SIGNATURE_MAX]
