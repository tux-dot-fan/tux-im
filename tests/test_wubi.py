"""Tests for the Wubi input mode."""

from __future__ import annotations

from tux_im.input.lexicon import Trie
from tux_im.input.wubi import WubiMode


class _FakeConfig:
    class ime:
        max_candidates = 9


def _letter(val):
    import gi

    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk

    return Gdk.unicode_to_keyval(ord(val))


def test_wubi_buffers_up_to_4_letters() -> None:
    trie = Trie()
    mode = WubiMode(trie, _FakeConfig)
    for ch in "kldw":
        assert mode.feed_key(_letter(ch), 0).handled
    assert mode.buffer == "kldw"
    # 5th letter is rejected.
    assert mode.feed_key(_letter("x"), 0) is None


def test_wubi_candidates() -> None:
    trie = Trie()
    trie.insert("kld", "我", 100)
    trie.insert("kldw", "我们", 80)
    mode = WubiMode(trie, _FakeConfig)
    mode.feed_key(_letter("k"), 0)
    mode.feed_key(_letter("l"), 0)
    mode.feed_key(_letter("d"), 0)
    cands = mode.candidates()
    assert cands[0].text == "我"
    assert any(c.text == "我们" for c in cands)
