"""Tests for the Pinyin input mode."""

from __future__ import annotations

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus  # noqa: E402

from tux_im.input.pinyin import PinyinMode


class _FakeConfig:
    class ime:
        max_candidates = 9


def _letter(val: str) -> int:
    """Map an ascii char to its IBus keyval (no Gdk needed)."""
    return IBus.keyval_from_name(val)


def _digit(val: str) -> int:
    """Map an ascii digit char to its IBus keyval."""
    return IBus.keyval_from_name(val)


def test_feed_letters() -> None:
    from tux_im.input.lexicon import Trie

    trie = Trie()
    trie.insert("ni3", "你", 100)
    trie.insert("ni3", "泥", 50)
    trie.insert("hao3", "好", 80)
    mode = PinyinMode(trie, _FakeConfig)

    r = mode.feed_key(_letter("n"), 0)
    assert r.handled
    assert mode.buffer == "n"
    r = mode.feed_key(_letter("i"), 0)
    assert r.handled
    r = mode.feed_key(_digit("3"), 0)
    assert r.handled
    assert mode.buffer == "ni3"
    cands = mode.candidates()
    assert any(c.text == "你" for c in cands)


def test_tone_after_letter() -> None:
    from tux_im.input.lexicon import Trie

    trie = Trie()
    mode = PinyinMode(trie, _FakeConfig)
    mode.feed_key(_letter("a"), 0)
    assert mode.feed_key(_digit("3"), 0).handled
    assert mode.buffer == "a3"


def test_digit_without_letter_ignored() -> None:
    from tux_im.input.lexicon import Trie

    trie = Trie()
    mode = PinyinMode(trie, _FakeConfig)
    assert mode.feed_key(_digit("3"), 0) is None


def test_reset() -> None:
    from tux_im.input.lexicon import Trie

    trie = Trie()
    mode = PinyinMode(trie, _FakeConfig)
    mode.feed_key(_letter("n"), 0)
    mode.reset()
    assert mode.buffer == ""


def test_select_first_candidate() -> None:
    from tux_im.input.lexicon import Trie

    trie = Trie()
    trie.insert("ni3", "你", 100)
    mode = PinyinMode(trie, _FakeConfig)
    mode.feed_key(_letter("n"), 0)
    mode.feed_key(_letter("i"), 0)
    mode.feed_key(_digit("3"), 0)
    r = mode.select(0)
    assert r.handled
    assert r.commit == "你"
    assert r.clear
    # Engine calls mode.reset() when result.clear is True;
    # simulate that since we're testing the mode directly.
    if r.clear:
        mode.reset()
    assert mode.buffer == ""
