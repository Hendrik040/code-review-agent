"""Jev as the yes/no judge in the Learnings layer (Phase 7).

Two decisions used to be Haiku calls:

  - Is this past learning applicable to the new diff? (every review,
    once per retrieved hit — shared/learnings.py)
  - Is this free-form @mention a learning at all? (capture daemon —
    learnings/capture.py)

Both are classifications, which is what Jev does: it returns a
probability instead of a word we then have to parse. With
TYPESAFE_API_KEY set, Jev judges; any Jev failure hands the decision
back to the Haiku path, so behavior without a key is unchanged.

One difference from Haiku on the capture side: Haiku also condensed
the comment into a lesson. Jev cannot write text, so a Jev-accepted
mention stores the maintainer's own paragraph, minus the handle.
Set LEARNINGS_JUDGE=haiku to keep the old behavior.
"""

from __future__ import annotations

import os
from typing import Any

from shared import jev

# Below this P(applicable) a hit is dropped. The Haiku judge kept "yes"
# and "maybe" and dropped "no"; this is the "no" line. Untuned.
DEFAULT_DROP_BELOW = 0.30
_YES_AT = 0.60          # label only: "yes" and "maybe" are both kept
_LEARNING_AT = 0.50


def enabled() -> bool:
    """LEARNINGS_JUDGE=auto (default) uses Jev when a key is set;
    =haiku never uses Jev."""
    mode = os.environ.get("LEARNINGS_JUDGE", "auto").strip().lower()
    return mode != "haiku" and jev.has_key()


def applicability(payload: dict[str, Any], file_diff: str, *, client: Any = None) -> str:
    """'yes' | 'maybe' | 'no' for one retrieved learning. Raises on Jev failure."""
    if not file_diff:
        # Same rule as the Haiku judge: no hunks for this file means we
        # can't judge, and an unjudged hit is not silently dropped.
        return "maybe"
    state = (
        f"PAST LEARNING:\n{payload.get('learning_text', '')}\n\n"
        f"PAST CODE ANCHOR ({payload.get('file_path', '')}:"
        f"{payload.get('line_start', '')}-{payload.get('line_end', '')}):\n"
        f"{payload.get('code_chunk_text', '')}\n\n"
        f"NEW DIFF FOR {payload.get('file_path', '')}:\n{file_diff}"
    )
    p = jev.yes_probability(
        state,
        "Is the past learning applicable to the new diff?",
        yes="The new diff touches or repeats the pattern the past learning "
            "is about, so a reviewer should keep the learning in mind.",
        no="The new diff has nothing to do with what the past learning is about.",
        client=client,
    )
    drop_below = float(os.environ.get("LEARNINGS_JEV_DROP_BELOW", DEFAULT_DROP_BELOW))
    if p < drop_below:
        return "no"
    return "yes" if p >= _YES_AT else "maybe"


def is_learning(body: str, *, parent_bot_comment: str = "", client: Any = None) -> bool:
    """Is this maintainer comment guidance the bot should remember? Raises on Jev failure."""
    state = (
        f"PARENT BOT FINDING:\n{parent_bot_comment or '(none)'}\n\n"
        f"MAINTAINER COMMENT:\n{body}"
    )
    p = jev.yes_probability(
        state,
        "Is the maintainer's comment a correction or guidance that a code "
        "review bot should remember for future reviews of this codebase?",
        yes="It states a rule, convention, or correction about the code or "
            "about how to review it.",
        no="It is thanks, a question, small talk, or a remark with no lasting "
           "guidance.",
        client=client,
    )
    return p >= _LEARNING_AT
