"""Jev (TypeSafe System One) access for the places we ask it something:
per-PR model routing (shared/routing.py) and the Learnings-layer judges
(learnings/jev_judge.py).

Jev writes no text. You send a `state` and typed questions, and get a
probability per answer. Callers own the fallback: everything here
raises, so a caller that must fail open wraps its own call.
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_TIMEOUT_S = 10.0


def has_key() -> bool:
    return bool(os.environ.get("TYPESAFE_API_KEY", "").strip())


def ask(
    state: Any,
    questions: dict[str, dict[str, Any]],
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
    client: Any = None,
) -> Any:
    """One System One call. `client` is the test seam."""
    if client is not None:
        return client.system_one(state=state, questions=questions)
    # Imported here so a missing SDK (Python 3.10) is a caller-handled
    # failure, not an import error for every module that touches Jev.
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    # One retry: Jev sits in front of other work and must not hold it up.
    with TypeSafeClient(timeout=timeout, retry=RetryPolicy(max_retries=1)) as c:
        return c.system_one(state=state, questions=questions)


def yes_probability(
    state: Any,
    instructions: str,
    *,
    yes: str | None = None,
    no: str | None = None,
    client: Any = None,
) -> float:
    """Ask one yes/no question; return P(yes) in [0, 1]."""
    question: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if yes or no:
        question["criteria"] = {"true": yes, "false": no}
    resp = ask(state, {"q": question}, client=client)
    return float(resp.nouls["q"].noul)
