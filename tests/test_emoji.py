"""Tests for the emoji input mode."""

from __future__ import annotations

import pytest

from tux_im.input.emoji import EmojiMode


class _DummyConfig:
    pass


@pytest.fixture
def mode() -> EmojiMode:
    return EmojiMode(_DummyConfig())


def _kv(c: str) -> int:
    """Convert a character to a Gdk keyval."""
    from gi.repository import Gdk
    return Gdk.unicode_to_keyval(ord(c))


def test_emoji_trigger_colon(mode: EmojiMode) -> None:
    """A single colon enters emoji mode (buffer stays empty)."""
    r = mode.feed_key(_kv(":"), 0)
    assert r is not None
    assert r.handled is True
    # Colon is the switch signal; buffer stays empty.
    assert mode.buffer == ""


def test_emoji_keyword_builds(mode: EmojiMode) -> None:
    """After colon, typing a-z chars builds the keyword buffer."""
    mode.feed_key(_kv(":"), 0)  # enter emoji mode
    for ch in "cat":
        r = mode.feed_key(_kv(ch), 0)
        assert r is not None
        assert r.handled is True
    assert mode.buffer == "cat"


def test_emoji_no_match_empty(mode: EmojiMode) -> None:
    """If no keyword has been typed, no candidates."""
    assert mode.candidates() == []


def test_emoji_candidates_found(mode: EmojiMode) -> None:
    """Typing ':cat' shows the cat emoji as a candidate.

    candidates().text is the emoji character (what gets committed).
    candidates().display is the keyword (what the user sees in the list).
    """
    mode.feed_key(_kv(":"), 0)
    mode.feed_key(_kv("c"), 0)
    mode.feed_key(_kv("a"), 0)
    mode.feed_key(_kv("t"), 0)
    cands = mode.candidates()
    assert len(cands) >= 1
    # The candidate's display is the keyword "cat"; its text is the emoji char.
    assert any(c.display == "cat" for c in cands)
    # The emoji char itself should be the candidate's text (for commit).
    assert any(c.text == "🐱" for c in cands)


def test_emoji_select_commits_emoji_char(mode: EmojiMode) -> None:
    """select() returns the emoji character as commit, not the keyword."""
    mode.feed_key(_kv(":"), 0)
    mode.feed_key(_kv("c"), 0)
    mode.feed_key(_kv("a"), 0)
    mode.feed_key(_kv("t"), 0)
    cands = mode.candidates()
    # Find index of "cat" (display) in candidates
    cat_idx = next(i for i, c in enumerate(cands) if c.display == "cat")
    r = mode.select(cat_idx)
    assert r.commit == "🐱"
    assert r.clear is True


def test_emoji_out_of_range_returns_false(mode: EmojiMode) -> None:
    """select(-1) and select(99) return handled=False."""
    mode.feed_key(_kv(":"), 0)
    mode.feed_key(_kv("c"), 0)
    mode.feed_key(_kv("a"), 0)
    mode.feed_key(_kv("t"), 0)
    assert mode.select(-1).handled is False
    assert mode.select(99).handled is False


def test_emoji_reset_clears_buffer(mode: EmojiMode) -> None:
    """reset() clears the keyword buffer."""
    mode.feed_key(_kv(":"), 0)
    mode.feed_key(_kv("c"), 0)
    mode.feed_key(_kv("a"), 0)
    mode.feed_key(_kv("t"), 0)
    assert mode.buffer == "cat"
    mode.reset()
    assert mode.buffer == ""


def test_emoji_page_navigation(mode: EmojiMode) -> None:
    """page() changes the offset; returns handled=True."""
    mode.feed_key(_kv(":"), 0)
    mode.feed_key(_kv("s"), 0)  # many "s*" keywords
    r_next = mode.page(1)
    assert r_next.handled is True
    r_prev = mode.page(-1)
    assert r_prev.handled is True


def test_emoji_second_colon_commits_literal(mode: EmojiMode) -> None:
    """Typing a second colon before any keyword commits ':' and exits."""
    mode.feed_key(_kv(":"), 0)  # enter
    r = mode.feed_key(_kv(":"), 0)  # second colon
    assert r is not None
    assert r.commit == ":"
    assert mode.buffer == ""


def test_emoji_non_alnum_resets_mode(mode: EmojiMode) -> None:
    """A non-alnum key (space) exits emoji mode.

    Emoji mode returns handled=False so the engine can process the key
    normally.  The emoji state is reset; a subsequent colon re-enters.
    """
    mode.feed_key(_kv(":"), 0)  # enter emoji mode
    mode.feed_key(_kv("c"), 0)  # type partial keyword "c"
    r = mode.feed_key(_kv(" "), 0)  # space: exits emoji mode
    assert r.handled is False
    # After space, emoji mode is inactive (buffer cleared).
    # A new colon re-enters emoji mode from scratch.
    mode.feed_key(_kv(":"), 0)
    mode.feed_key(_kv("d"), 0)
    assert mode.buffer == "d"
