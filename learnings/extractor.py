"""@mention parser for capture pipeline.

Builds the regex dynamically from the configured handle + call-word list
(both ``re.escape``'d) so users can rebrand without code changes. Spec §4.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Mention:
    call_word: str       # the matched call word, as written by the maintainer
    text: str            # the captured learning text, whitespace-normalized


class Extractor:
    def __init__(self, handle: str, call_words: tuple[str, ...]) -> None:
        if not call_words:
            raise ValueError("at least one call word required")
        words_alt = "|".join(re.escape(w) for w in call_words)
        pattern = (
            re.escape(handle)
            + r"\s+(" + words_alt + r")\b\s*[:.\-]?\s*(.+?)(?:\n\s*\n|\Z)"
        )
        # DOTALL lets the body span multiple lines; the (?:\n\s*\n|\Z)
        # terminator stops the capture at the first blank line so trailing
        # PR-comment prose doesn't end up embedded in the learning text.
        self._re = re.compile(pattern, re.IGNORECASE | re.DOTALL)

    def parse(self, body: str) -> Mention | None:
        """Return the FIRST mention in body, or None.

        Bodies with multiple `@handle <call-word> ...` mentions are not
        supported — only the first is captured. This matches Spec §4's
        "one learning per comment" contract.
        """
        m = self._re.search(body)
        if not m:
            return None
        text = " ".join(m.group(2).split())  # collapse whitespace, drop newlines
        if not text:
            return None
        return Mention(call_word=m.group(1), text=text)
