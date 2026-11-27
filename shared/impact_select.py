"""Choose which ODIS impact candidates the reviewer sees (Phase 8, host side).

`decide` takes the document `python -m shared.odis_cli collect` prints and
returns the decisions `render` consumes. When every candidate fits the
impact budget it returns `tiers=None` (today's context, byte for byte)
without calling Jev. Otherwise Jev answers one yes/no question per
candidate: is this the actual definition or call site the changed code
refers to? Scores become tiers in shared/impact.py.

Selection never fails the review. No key, a missing SDK, an error, the
overall deadline, or a malformed answer all degrade to the fixed order
in `impact.fallback_key`; answers that did arrive are kept.

Host only: this module talks to Jev and must never be uploaded into the
sandbox (it is not in sandbox/daytona.py::_HOST_SHARED_FILES).
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from shared import impact, jev

log = logging.getLogger("shared.impact_select")

QUESTION = (
    "Candidate `candidates.{cid}` was found by name matching. Is it the actual "
    "definition or call site that the changed code in `diff` refers to, so that a "
    "reviewer needs to see it to judge whether the change is correct?"
)

# Jev's request limit is about 32k tokens. Characters / 3 overestimates
# tokens for code, so 72,000 characters keeps a request near 24k tokens.
_MAX_REQUEST_CHARS = 72_000
_MAX_DIFF_CHARS = 24_000
# What a signature line adds to the context, for the total-size guard.
_SIGNATURE_CHARS = 200

_MODES = ("jev", "cap", "off")


@dataclass(frozen=True)
class Config:
    mode: str
    keep: float
    mention: float
    budget: int
    max_signatures: int
    context_max: int
    timeout: float


def _env_number(name: str, default: float, cast=float):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return cast(default)
    try:
        return cast(raw)
    except ValueError:
        log.warning("impact_select: ignoring %s=%r, using %s", name, raw, default)
        return cast(default)


def load_config() -> Config:
    """Read the IMPACT_* / CONTEXT_MAX_CHARS environment at call time."""
    raw = os.environ.get("IMPACT_SELECT", "").strip().lower()
    if not raw:
        mode = "jev" if jev.has_key() else "cap"
    elif raw in _MODES:
        mode = raw
    else:
        log.warning("impact_select: unknown IMPACT_SELECT=%r, using cap", raw)
        mode = "cap"
    return Config(
        mode=mode,
        keep=_env_number("IMPACT_KEEP", 0.5),
        mention=_env_number("IMPACT_MENTION", 0.2),
        budget=_env_number("IMPACT_MAX_CHARS", 12_000, int),
        max_signatures=_env_number("IMPACT_MAX_SIGNATURES", 20, int),
        context_max=_env_number("CONTEXT_MAX_CHARS", 60_000, int),
        timeout=_env_number("IMPACT_SELECT_TIMEOUT", 10.0),
    )


def _batches(diff: str, candidates: list[dict]) -> list[tuple[dict, dict]]:
    """Pack candidates into (state, questions) pairs under the size limit.
    Every request carries the same (truncated) diff."""
    base = len(json.dumps({"diff": diff, "candidates": {}})) + 2
    out: list[tuple[dict, dict]] = []
    state_c: dict[str, dict] = {}
    questions: dict[str, dict] = {}
    used = base
    for c in candidates:
        q = {"type": "noul", "instructions": QUESTION.format(cid=c["id"])}
        cost = len(json.dumps({c["id"]: c["summary"]})) + len(json.dumps({c["id"]: q}))
        if state_c and used + cost > _MAX_REQUEST_CHARS:
            out.append(({"diff": diff, "candidates": state_c}, questions))
            state_c, questions, used = {}, {}, base
        state_c[c["id"]] = c["summary"]
        questions[c["id"]] = q
        used += cost
    if state_c:
        out.append(({"diff": diff, "candidates": state_c}, questions))
    return out


def _valid(p: Any) -> bool:
    return isinstance(p, (int, float)) and math.isfinite(p) and 0.0 <= p <= 1.0


def score(
    diff: str, candidates: list[dict], *, timeout: float, client: Any = None,
) -> tuple[dict[str, float], int, str]:
    """Ask Jev about every candidate. Returns (scores, requests, error):
    scores holds only valid answers that arrived before the deadline;
    error is "" when every request answered. Never raises."""
    requests = _batches(diff[:_MAX_DIFF_CHARS], candidates)
    scores: dict[str, float] = {}
    errors: list[str] = []
    pool = ThreadPoolExecutor(max_workers=min(8, len(requests)) or 1)
    try:
        futures = {
            pool.submit(jev.ask, state, qs, timeout=timeout, client=client): qs
            for state, qs in requests
        }
        done, pending = wait(futures, timeout=timeout)
        if pending:
            errors.append(f"{len(pending)} of {len(requests)} requests missed the {timeout:g}s deadline")
        for f in done:
            try:
                resp = f.result()
            except Exception as e:  # noqa: BLE001 — selection must not fail the review
                errors.append(f"{type(e).__name__}: {e}")
                continue
            nouls = getattr(resp, "nouls", {}) or {}
            for cid in futures[f]:
                ans = nouls.get(cid)
                p = getattr(ans, "noul", None)
                if _valid(p):
                    scores[cid] = float(p)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return scores, len(requests), "; ".join(errors)


def _as_candidate(d: dict) -> SimpleNamespace:
    s = d["summary"]
    return SimpleNamespace(
        id=d["id"], role=s["role"], file=s["file"], line=s["line"],
        symbol=s["symbol"], line_text=s.get("line_text", ""),
        doc=s.get("docstring_first_line", ""),
        inside_function=s.get("inside_function", ""), **d["facts"],
    )


def decide(doc: dict, cfg: Config, *, client: Any = None) -> tuple[dict, dict]:
    """Decisions for `odis_cli render`, plus a log record. Call with
    cfg.mode "jev" or "cap"; "off" never reaches here."""
    started = time.monotonic()
    cands = doc["candidates"]
    sizes = {c["id"]: int(c["size"]) for c in cands}
    record = {"path": "small", "reason": "", "candidates": len(cands),
              "tiers": {impact.FULL: len(cands), impact.SIGNATURE: 0, impact.COUNTED: 0},
              "jev_ms": 0, "requests": 0}
    base_chars = len(doc["diff"]) + int(doc.get("changed_chars", 0))

    if sum(sizes.values()) <= cfg.budget:
        decisions = {"tiers": None, "note": "",
                     "drop_changed": base_chars + sum(sizes.values()) > cfg.context_max}
        _log(record)
        return decisions, record

    objs = impact.dedupe([_as_candidate(c) for c in cands])
    live = [c for c in cands if c["id"] in {o.id for o in objs}]
    scores: dict[str, float] = {}
    if cfg.mode != "jev":
        record.update(path="fallback", reason="cap mode")
    elif client is None and not jev.has_key():
        record.update(path="fallback", reason="no TYPESAFE_API_KEY")
    else:
        t0 = time.monotonic()
        scores, requests, error = score(doc["diff"], live, timeout=cfg.timeout, client=client)
        record.update(jev_ms=int((time.monotonic() - t0) * 1000), requests=requests)
        if scores:
            record.update(path="jev", reason=error)
        else:
            record.update(path="fallback", reason=error or "no valid answers")

    tiers = impact.assign_tiers(
        objs, sizes, scores or None, keep=cfg.keep, mention=cfg.mention,
        budget=cfg.budget, max_signatures=cfg.max_signatures,
    )
    note = impact.not_shown_note(objs, tiers, ranked=bool(scores))
    counts = {t: list(tiers.values()).count(t) for t in (impact.FULL, impact.SIGNATURE, impact.COUNTED)}
    impact_chars = (
        sum(sizes[i] for i, t in tiers.items() if t == impact.FULL)
        + _SIGNATURE_CHARS * counts[impact.SIGNATURE] + len(note)
    )
    record["tiers"] = counts
    record["total_ms"] = int((time.monotonic() - started) * 1000)
    _log(record)
    return {"tiers": tiers, "note": note,
            "drop_changed": base_chars + impact_chars > cfg.context_max}, record


def _log(r: dict) -> None:
    t = r["tiers"]
    log.info(
        "impact_select path=%s reason=%s candidates=%d full=%d signature=%d "
        "counted=%d jev_ms=%d requests=%d",
        r["path"], r["reason"] or "-", r["candidates"], t[impact.FULL],
        t[impact.SIGNATURE], t[impact.COUNTED], r["jev_ms"], r["requests"],
    )
