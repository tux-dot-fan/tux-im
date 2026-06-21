"""Tests for the Wbpy (mixed) input mode."""

from __future__ import annotations

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus  # noqa: E402

from tux_im.input.lexicon import Trie
from tux_im.input.wbpy import WbpyMode


class _FakeConfig:
    class ime:
        max_candidates = 9


def _letter(val: str) -> int:
    """Map an ascii char to its IBus keyval (no Gdk needed)."""
    return IBus.keyval_from_name(val)


def _digit(val: str) -> int:
    """Map an ascii digit char to its IBus keyval."""
    return IBus.keyval_from_name(val)


def test_wbpy_merges_candidates() -> None:
    pinyin = Trie()
    pinyin.insert("ni3", "你", 100)
    wubi = Trie()
    wubi.insert("kld", "我", 100)
    mode = WbpyMode(pinyin, _FakeConfig)
    mode.attach_wubi(wubi)

    # Type wubi code.
    for ch in "kld":
        mode.feed_key(_letter(ch), 0)
    cands = mode.candidates()
    assert any(c.text == "我" for c in cands)


def test_wbpy_pinyin_lookup() -> None:
    pinyin = Trie()
    pinyin.insert("ni3", "你", 100)
    wubi = Trie()
    mode = WbpyMode(pinyin, _FakeConfig)
    mode.attach_wubi(wubi)

    for ch in "ni":
        mode.feed_key(_letter(ch), 0)
    mode.feed_key(_digit("3"), 0)
    cands = mode.candidates()
    assert any(c.text == "你" for c in cands)
