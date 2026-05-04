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


def test_only_first_mention_captured(ex: Extractor):
    """Pin the contract: bodies with multiple mentions yield only the first.
    See Spec §4 — one learning per comment body."""
    body = (
        "@Working-Ant learn first lesson\n\n"
        "@Working-Ant note second lesson"
    )
    m = ex.parse(body)
    assert m is not None
    assert m.call_word == "learn"
    assert m.text == "first lesson"
    # The second mention is dropped, not concatenated.
    assert "@Working-Ant" not in m.text
    assert "second" not in m.text


def test_trailing_prose_after_blank_line_is_dropped(ex: Extractor):
    """Maintainers often write a learning then continue normal review prose;
    the prose must not end up embedded in the learning text."""
    body = (
        "@Working-Ant teach use .$apply not Reflect.apply\n\n"
        "LGTM otherwise — please also rename foo to bar."
    )
    m = ex.parse(body)
    assert m is not None
    assert m.call_word == "teach"
    assert m.text == "use .$apply not Reflect.apply"
    assert "LGTM" not in m.text
    assert "rename" not in m.text


def test_single_line_body_still_works(ex: Extractor):
    """The blank-line terminator must not break the single-line common case."""
    m = ex.parse("@Working-Ant learn always X")
    assert m == Mention(call_word="learn", text="always X")


def test_multi_line_within_one_paragraph_collapsed(ex: Extractor):
    """Newlines INSIDE the same paragraph (no blank line between) collapse
    into spaces — already covered by test_multi_line_body_collapsed but
    pin it here in the new termination semantics too."""
    m = ex.parse("@Working-Ant teach line one\nline two\nline three")
    assert m == Mention(call_word="teach", text="line one line two line three")


# ---------------------------------------------------------------------------
# Phase 6.1: Haiku-based classifier fallback for free-form @mentions.
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock


def _fake_haiku(text: str) -> MagicMock:
    """Build an anthropic-shaped MagicMock returning the given text."""
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    client.messages.create.return_value = msg
    return client


def test_classify_via_llm_extracts_lesson_when_yes():
    ex = Extractor(handle="@Working-Ant", call_words=("learn",))
    client = _fake_haiku('{"is_learning": true, "lesson_text": "always use X"}')
    m = ex.classify_via_llm(
        "@Working-Ant that, in this case, please remember to always use X",
        anthropic_client=client,
    )
    assert m == Mention(call_word="(llm)", text="always use X")


def test_classify_via_llm_returns_none_when_no():
    ex = Extractor(handle="@Working-Ant", call_words=("learn",))
    client = _fake_haiku('{"is_learning": false, "lesson_text": ""}')
    m = ex.classify_via_llm("@Working-Ant thanks!", anthropic_client=client)
    assert m is None


def test_classify_via_llm_tolerates_json_code_fence():
    ex = Extractor(handle="@Working-Ant", call_words=("learn",))
    client = _fake_haiku('```json\n{"is_learning": true, "lesson_text": "be careful"}\n```')
    m = ex.classify_via_llm("@Working-Ant be careful", anthropic_client=client)
    assert m == Mention(call_word="(llm)", text="be careful")


def test_classify_via_llm_returns_none_on_haiku_exception():
    ex = Extractor(handle="@Working-Ant", call_words=("learn",))
    client = MagicMock()
    client.messages.create.side_effect = Exception("haiku unreachable")
    m = ex.classify_via_llm("@Working-Ant remember X", anthropic_client=client)
    assert m is None


def test_classify_via_llm_returns_none_on_malformed_json():
    ex = Extractor(handle="@Working-Ant", call_words=("learn",))
    client = _fake_haiku('this is not json at all')
    m = ex.classify_via_llm("@Working-Ant remember X", anthropic_client=client)
    assert m is None


def test_classify_via_llm_includes_parent_bot_finding_in_prompt():
    ex = Extractor(handle="@Working-Ant", call_words=("learn",))
    client = _fake_haiku('{"is_learning": true, "lesson_text": "ok"}')
    ex.classify_via_llm(
        "@Working-Ant this is fine here",
        anthropic_client=client,
        parent_bot_comment="The items table declares user_id INTEGER...",
    )
    # Verify the prompt included the parent text.
    call_kwargs = client.messages.create.call_args.kwargs
    prompt_text = call_kwargs["messages"][0]["content"]
    assert "items table declares user_id INTEGER" in prompt_text
    assert "MAINTAINER COMMENT:" in prompt_text
    assert "PARENT BOT FINDING:" in prompt_text
