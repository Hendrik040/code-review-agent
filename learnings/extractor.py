"""@mention parser for capture pipeline.

Builds the regex dynamically from the configured handle + call-word list
(both ``re.escape``'d) so users can rebrand without code changes. Spec §4.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


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
        self._handle_lower_cached = handle.lower()

    def _handle_lower(self) -> str:
        """Lowercased handle for membership checks."""
        return self._handle_lower_cached

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

    def classify_via_llm(
        self, body: str, *,
        anthropic_client: Any,
        parent_bot_comment: str = "",
        model: str = "claude-haiku-4-5-20251001",
    ) -> Mention | None:
        """LLM-based fallback: classify a free-form ``@handle`` mention as
        a learning or not, and extract the lesson text.

        Returns ``Mention | None``. Strictly fail-open: ANY exception
        (Haiku unreachable, malformed response, empty lesson) returns
        None — the daemon's per-comment except will then advance the
        cursor without storing anything (spec §8.1).

        The returned ``Mention.call_word`` is the sentinel ``"(llm)"`` to
        mark LLM-extracted mentions for downstream traceability (vs.
        regex-matched mentions which carry the literal call word).
        """
        prompt = (
            "You are deciding whether a maintainer's PR comment is a "
            "\"learning\" — a correction or guidance the bot should "
            "remember for future code reviews of this codebase.\n"
            "\n"
            "Return STRICT JSON only — no preamble, no markdown fence:\n"
            '  {"is_learning": <bool>, "lesson_text": "<string>"}\n'
            "\n"
            "If is_learning=false, lesson_text must be \"\".\n"
            "If is_learning=true, lesson_text is the extracted directive — "
            "strip conversational lead-in and fluff, keep just the "
            "actionable lesson the bot should remember.\n"
            "\n"
            f"PARENT BOT FINDING:\n{parent_bot_comment or '(none — comment is not a reply)'}\n"
            "\n"
            f"MAINTAINER COMMENT:\n{body}\n"
            "\n"
            "JSON:"
        )
        try:
            msg = anthropic_client.messages.create(
                model=model, max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = (msg.content[0].text or "").strip()
            # Tolerate ```json fences if Haiku adds them.
            if raw.startswith("```"):
                raw = raw.strip("`").lstrip("json").strip()
            parsed = json.loads(raw)
            if not parsed.get("is_learning"):
                return None
            lesson = (parsed.get("lesson_text") or "").strip()
            if not lesson:
                return None
            return Mention(call_word="(llm)", text=lesson)
        except Exception:
            return None
