"""Per-PR model routing (Phase 7) — one Jev call picks the reviewer tier.

Jev (TypeSafe System One) writes no text: it answers typed questions
about a `state` and returns a probability for each answer. We ask how
deep a review this diff needs, then pick the cheapest (model, effort)
tier whose chance of being too shallow is under ROUTER_RISK.

The decision is made ONCE, before the agent starts. A review is one
prompt plus a tool loop, and prompt caches are per model, so switching
models mid-review would re-pay the whole cached prefix.

Strictly additive, like the Learnings layer: no TYPESAFE_API_KEY, a
missing SDK (Python 3.10), a timeout or any API error returns the
caller's default tier — what the reviewer ran before routing existed.
"""

from __future__ import annotations

import logging
import os
import shlex
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

log = logging.getLogger("routing")

EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Cheapest → deepest. A tier's index is the Jev depth level it serves.
TIER_NAMES = ("light", "standard", "deep")
# "model:effort". `deep` has no entry: it defaults to whatever the caller
# passes as `default` (the reviewer's own MODEL/EFFORT), so an unrouted
# run and a deep-routed run are the same run.
_BUILTIN_TIERS = {
    "light": "claude-haiku-5-5:medium",
    "standard": "claude-sonnet-5-5:high",
}

# The cost of a wrong pick is asymmetric: too deep wastes money, too
# shallow misses bugs. So a downgrade needs Jev to be confident.
DEFAULT_RISK = 0.15
# High-stakes code gets the deep tier even when the diff looks small —
# a one-line change to an auth check is the case a depth rubric underrates.
HIGH_STAKES_FLOOR = 0.5
# Jev bills input tokens, so the diff is capped. The per-file line counts
# are always sent in full, so size stays visible when the diff is cut.
DEFAULT_MAX_DIFF_CHARS = 24_000
DEFAULT_TIMEOUT_S = 10.0

QUESTIONS: dict[str, dict[str, Any]] = {
    "depth": {
        "type": "score",
        "instructions": (
            "How much investigation does a code reviewer need to reliably "
            "find every real bug in this pull request?"
        ),
        "criteria": [
            "None: documentation, comments, formatting, renames, version "
            "bumps or generated files only. No behavior change.",
            "Local: a behavior change in one place that can be judged from "
            "the diff and the functions it touches.",
            "Deep: correctness depends on code outside the diff, such as "
            "changed contracts with callers elsewhere, concurrency, state "
            "machines, migrations or subtle invariants.",
        ],
    },
    "high_stakes": {
        "type": "noul",
        "instructions": (
            "Does this change touch authentication, authorization, secrets, "
            "payments, data deletion or migration, or concurrency primitives?"
        ),
    },
}


@dataclass(frozen=True)
class Tier:
    name: str
    model: str
    effort: str


@dataclass(frozen=True)
class Decision:
    tier: Tier
    source: str  # "jev" | "default"
    reason: str
    depth_probs: tuple[float, ...] = ()
    high_stakes: float | None = None

    def describe(self) -> str:
        return (
            f"{self.tier.name} ({self.tier.model}, effort={self.tier.effort}) "
            f"via {self.source}: {self.reason}"
        )


def _parse_tier(name: str, spec: str) -> Tier:
    model, sep, effort = spec.strip().rpartition(":")
    if not sep or not model or effort not in EFFORTS:
        raise ValueError(f"tier {name!r} must be 'model:effort', got {spec!r}")
    return Tier(name, model, effort)


def load_tiers(default: Tier) -> list[Tier]:
    """Tiers cheapest → deepest. ROUTER_TIER_<NAME>=model:effort overrides
    one; set all three to the same model to route effort only."""
    load_dotenv(override=True)  # callers may ask for tiers without route()
    tiers = []
    for name in TIER_NAMES:
        spec = os.environ.get(f"ROUTER_TIER_{name.upper()}", "").strip()
        spec = spec or _BUILTIN_TIERS.get(name, "")
        tiers.append(
            _parse_tier(name, spec) if spec
            else Tier(name, default.model, default.effort)
        )
    return tiers


def pick_level(
    depth_probs: tuple[float, ...], high_stakes: float, risk: float
) -> tuple[int, str]:
    """Cheapest level whose chance of needing a deeper one is <= risk."""
    top = len(depth_probs) - 1
    if high_stakes >= HIGH_STAKES_FLOOR:
        return top, f"high-stakes p={high_stakes:.2f}"
    for level in range(top):
        p_deeper = sum(depth_probs[level + 1:])
        if p_deeper <= risk + 1e-9:  # 0.10 + 0.05 is 0.15000000000000002
            return level, f"P(needs deeper)={p_deeper:.2f} <= {risk:.2f}"
    return top, f"P(needs deep)={depth_probs[top]:.2f} > {risk:.2f}"


def build_state(
    repo: Any, base_ref: str, head_ref: str, title: str | None, max_chars: int
) -> str:
    """What Jev judges: title, per-file line counts, and the diff."""
    rng = f"{shlex.quote(base_ref)}..{shlex.quote(head_ref)}"
    stat = repo.exec(f"git diff --numstat {rng}", timeout=30)
    diff = repo.exec(f"git diff {rng}", timeout=30)
    if stat.exit_code != 0 or diff.exit_code != 0 or not diff.stdout.strip():
        raise ValueError("no diff to route on")
    text, shown = diff.stdout, diff.stdout[:max_chars]
    cut = f" (first {len(shown)} of {len(text)} characters)" if len(shown) < len(text) else ""
    parts = [
        f"Pull request title: {title}" if title else "",
        "Files changed (lines added, lines removed, path):",
        stat.stdout.strip(),
        f"Diff{cut}:",
        shown,
    ]
    return "\n".join(p for p in parts if p)


def _ask_jev(state: str, client: Any, timeout: float) -> Any:
    if client is not None:
        return client.system_one(state=state, questions=QUESTIONS)
    # Imported here so a missing SDK is a fallback, not an import error.
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    # One retry: a slow router must not hold up the review it is routing.
    with TypeSafeClient(timeout=timeout, retry=RetryPolicy(max_retries=1)) as c:
        return c.system_one(state=state, questions=QUESTIONS)


def route(
    repo: Any,
    base_ref: str,
    head_ref: str,
    *,
    default: Tier,
    title: str | None = None,
    client: Any = None,
) -> Decision:
    """Pick the reviewer tier for this diff. Never raises."""
    load_dotenv(override=True)
    if client is None and not os.environ.get("TYPESAFE_API_KEY", "").strip():
        return Decision(default, "default", "TYPESAFE_API_KEY not set")
    try:
        tiers = load_tiers(default)
        risk = float(os.environ.get("ROUTER_RISK", DEFAULT_RISK))
        max_chars = int(os.environ.get("ROUTER_MAX_DIFF_CHARS", DEFAULT_MAX_DIFF_CHARS))
        timeout = float(os.environ.get("ROUTER_TIMEOUT", DEFAULT_TIMEOUT_S))
        state = build_state(repo, base_ref, head_ref, title, max_chars)
        resp = _ask_jev(state, client, timeout)
        raw = resp.scores["depth"].probabilities
        probs = tuple(float(raw.get(i, 0.0)) for i in range(len(TIER_NAMES)))
        # A distribution that doesn't cover our three levels means Jev
        # answered a different rubric than we asked; don't route on it.
        if abs(sum(probs) - 1.0) > 0.1:
            raise ValueError("depth probabilities do not sum to 1")
        high_stakes = float(resp.nouls["high_stakes"].noul)
        level, why = pick_level(probs, high_stakes, risk)
        return Decision(tiers[level], "jev", why, probs, high_stakes)
    except Exception as e:  # noqa: BLE001 — boundary; routing is fail-open
        # Class name only: SDK errors can carry request URLs and bodies.
        log.warning("routing: using default tier (%s)", type(e).__name__)
        return Decision(default, "default", f"Jev unavailable ({type(e).__name__})")
