"""Mention extractor — regex built from configured handle + call words."""
from __future__ import annotations

import pytest

from learnings.extractor import Extractor, Mention

DEFAULT_WORDS = ("learn", "remember", "note", "teach")


@pytest.fixture
def ex() -> Extractor:
    return Extractor(handle="@Working-Ant", call_words=DEFAULT_WORDS)


def test_basic_mention(ex: Extractor):
    m = ex.parse("@Working-Ant learn always use .$apply")
    assert m == Mention(call_word="learn", text="always use .$apply")


def test_handle_case_insensitive(ex: Extractor):
    m = ex.parse("@working-ant remember: handle nulls")
    assert m == Mention(call_word="remember", text="handle nulls")


def test_call_word_case_insensitive(ex: Extractor):
    m = ex.parse("@Working-Ant LEARN: x")
    assert m == Mention(call_word="LEARN", text="x")


def test_optional_punctuation(ex: Extractor):
    assert ex.parse("@Working-Ant note - foo") == Mention(call_word="note", text="foo")
    assert ex.parse("@Working-Ant note: foo") == Mention(call_word="note", text="foo")
    assert ex.parse("@Working-Ant note. foo") == Mention(call_word="note", text="foo")
    assert ex.parse("@Working-Ant note foo") == Mention(call_word="note", text="foo")


def test_multi_line_body_collapsed(ex: Extractor):
    assert ex.parse("@Working-Ant teach\nfoo bar baz") == Mention(call_word="teach", text="foo bar baz")


def test_wrong_handle_returns_none(ex: Extractor):
    assert ex.parse("@OtherBot learn x") is None


def test_wrong_call_word_returns_none(ex: Extractor):
    assert ex.parse("@Working-Ant fix x") is None


def test_empty_text_returns_none(ex: Extractor):
    assert ex.parse("@Working-Ant learn   ") is None


def test_normal_comment_returns_none(ex: Extractor):
    assert ex.parse("Looks good to me") is None


def test_extractor_escapes_handle_with_regex_chars():
    """LEARNINGS_HANDLE could contain regex metachars; must be escaped."""
    ex = Extractor(handle="@bot.x+y", call_words=DEFAULT_WORDS)
    assert ex.parse("@bot.x+y learn ok") == Mention(call_word="learn", text="ok")
    # The literal regex shouldn't loosely match a different handle.
    assert ex.parse("@botxxxy learn no") is None
