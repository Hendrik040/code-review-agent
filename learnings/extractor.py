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
            + r"\s+(" + words_alt + r")\b\s*[:.\-]?\s*(.+)"
        )
        # DOTALL lets the body span multiple lines (we collapse whitespace below).
        self._re = re.compile(pattern, re.IGNORECASE | re.DOTALL)

    def parse(self, body: str) -> Mention | None:
        m = self._re.search(body)
        if not m:
            return None
        text = " ".join(m.group(2).split())  # collapse whitespace, drop newlines
        if not text:
            return None
        return Mention(call_word=m.group(1), text=text)
