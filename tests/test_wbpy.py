"""Tests for the Wbpy (mixed) input mode.

Wbpy must:
  - Feed every key to BOTH the wubi engine and the google pinyin engine
    in parallel (not pick one based on a heuristic).
  - Display BOTH candidate lists in the lookup table — wubi cands first,
    pinyin cands second, deduplicated by text.
  - Handle tone digits (1-5) — they go to pinyin only and never break
    the wubi half.
"""

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
    return IBus.keyval_from_name(val)


def test_wbpy_wubi_candidates_shown() -> None:
    """A pure-wubi buffer must still produce wubi candidates."""
    pinyin = Trie()
    wubi = Trie()
    wubi.insert("kld", "我", 100)
    mode = WbpyMode(pinyin, _FakeConfig)
    mode.attach_wubi(wubi)
    for ch in "kld":
        mode.feed_key(_letter(ch), 0)
    cands = mode.candidates()
    assert any(c.text == "我" for c in cands), f"missing wubi cand: {cands}"


def test_wbpy_pinyin_candidates_shown_for_pure_pinyin_buffer() -> None:
    """A buffer the user types as pinyin must show pinyin candidates,
    not be silently swallowed by the wubi half."""
    pinyin = Trie()
    # Insert "ni" as a pinyin prefix so google pinyin's segmenter
    # produces a syllable.  GooglePinyinMode will also fall back to
    # the raw buffer when the decoder returns nothing, so even an
    # empty trie gives a non-empty candidate.
    wubi = Trie()
    mode = WbpyMode(pinyin, _FakeConfig)
    mode.attach_wubi(wubi)
    for ch in "ni":
        mode.feed_key(_letter(ch), 0)
    cands = mode.candidates()
    # The visible buffer is "ni" — google pinyin should produce a
    # candidate for this.  Even with an empty trie the google pinyin
    # engine returns the raw buffer as a fallback candidate.
    assert any(c.text for c in cands), f"no pinyin cands for 'ni': {cands}"


def test_wbpy_both_halves_populate_candidates() -> None:
    """In wbpy mode the user might type a buffer that is BOTH a valid
    wubi prefix AND a valid pinyin prefix.  The lookup table must
    contain candidates from BOTH halves.
    """
    pinyin = Trie()
    wubi = Trie()
    # "g" alone is a valid wubi prefix (lots of words start with g).
    # "g" alone is NOT a pinyin syllable on its own — but the google
    # pinyin decoder still treats the raw buffer as a candidate, so
    # we expect at least one candidate from the pinyin half.
    wubi.insert("gg", "钢", 100)
    mode = WbpyMode(pinyin, _FakeConfig)
    mode.attach_wubi(wubi)
    for ch in "gg":
        mode.feed_key(_letter(ch), 0)
    cands = mode.candidates()
    texts = [c.text for c in cands]
    assert "钢" in texts, f"missing wubi cand: {texts}"
    # The pinyin half should contribute at least one candidate too —
    # the google pinyin decoder's raw buffer fallback.
    assert len(cands) >= 2, f"expected both halves, got: {texts}"


def test_wbpy_tone_digit_does_not_corrupt_wubi() -> None:
    """After typing pinyin + tone, the wubi half should still work
    for a later letter input (wubi's buffer is kept separate from
    the visible buffer which contains the tone digit)."""
    pinyin = Trie()
    wubi = Trie()
    wubi.insert("kld", "我", 100)
    mode = WbpyMode(pinyin, _FakeConfig)
    mode.attach_wubi(wubi)
    # Type a pinyin syllable + tone.
    for ch in "ni":
        mode.feed_key(_letter(ch), 0)
    mode.feed_key(_digit("3"), 0)
    assert mode.buffer == "ni3"
    # Now type a wubi code on top — the wubi engine must NOT be
    # polluted by the "ni3" buffer.
    for ch in "kld":
        mode.feed_key(_letter(ch), 0)
    # Visible buffer is the concatenation of pinyin + wubi letters.
    cands = mode.candidates()
    texts = [c.text for c in cands]
    assert "我" in texts, f"wubi cand lost after pinyin+tone: {texts}"
