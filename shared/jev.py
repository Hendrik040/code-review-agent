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


def nouls(
    state: Any,
    questions: dict[str, dict[str, Any]],
    *,
    client: Any = None,
) -> dict[str, float]:
    """Ask several yes/no questions about one state in ONE request;
    return P(yes) per question name. Questions are answered in parallel,
    so a second question about the same state costs almost nothing."""
    resp = ask(state, questions, client=client)
    return {name: float(resp.nouls[name].noul) for name in questions}


def noul(instructions: str, *, yes: str | None = None, no: str | None = None) -> dict[str, Any]:
    """A yes/no question. `yes` / `no` say what counts as each answer."""
    question: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if yes or no:
        question["criteria"] = {"true": yes, "false": no}
    return question
