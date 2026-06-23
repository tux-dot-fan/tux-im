"""Tests for the Wubi input mode."""

from __future__ import annotations

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus  # noqa: E402

from tux_im.input.lexicon import Trie
from tux_im.input.wubi import WubiMode


class _FakeConfig:
    class Ime:
        max_candidates = 9

    ime = Ime


def _letter(val: str) -> int:
    """Map an ascii char to its IBus keyval (no Gdk needed)."""
    return IBus.keyval_from_name(val)


def test_wubi_buffers_up_to_4_letters() -> None:
    """Wubi buffers up to 4 letters only when they are valid wubi prefixes."""
    trie = Trie()
    # Insert entries so the trie knows 'k' is a valid wubi prefix.
    trie.insert("kldw", "我们", 80)
    trie.insert("kld", "我", 100)
    mode = WubiMode(trie, _FakeConfig)
    for ch in "kldw":
        assert mode.feed_key(_letter(ch), 0).handled
    assert mode.buffer == "kldw"
    # 5th letter is rejected: buffer is already at max len 4.
    assert mode.feed_key(_letter("x"), 0) is None


def test_wubi_candidates() -> None:
    trie = Trie()
    # Both words share the prefix "kld"; they are at the same terminal node.
    trie.insert("kld", "我", 100)
    trie.insert("kld", "我们", 80)
    mode = WubiMode(trie, _FakeConfig)
    mode.feed_key(_letter("k"), 0)
    mode.feed_key(_letter("l"), 0)
    mode.feed_key(_letter("d"), 0)
    cands = mode.candidates()
    # "我" ranks first (higher freq 100 > 80).
    assert cands[0].text == "我"
    assert any(c.text == "我们" for c in cands)
