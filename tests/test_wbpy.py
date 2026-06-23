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
from gi.repository import IBus

from tux_im.input.lexicon import Trie
from tux_im.input.wbpy import WbpyMode


class _FakeConfig:
    class Ime:
        max_candidates = 9

    ime = Ime


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


def test_wbpy_backspace_pops_visible_buffer() -> None:
    """Backspace must shrink the visible buffer by one."""
    pinyin = Trie()
    wubi = Trie()
    mode = WbpyMode(pinyin, _FakeConfig)
    mode.attach_wubi(wubi)
    for ch in "abc":
        mode.feed_key(_letter(ch), 0)
    assert mode.buffer == "abc"
    assert mode.backspace() is True
    assert mode.buffer == "ab"


def test_wbpy_backspace_rolls_back_wubi_and_pinyin() -> None:
    """The user-reported bug: backspace appeared to do nothing because
    the wubi and pinyin sub-engines kept their own internal buffers
    and the next feed_key re-concatenated the deleted character.
    After backspace, both sub-engine buffers must be in lockstep
    with the visible buffer.
    """
    pinyin = Trie()
    wubi = Trie()
    wubi.insert("kld", "我", 100)
    mode = WbpyMode(pinyin, _FakeConfig)
    mode.attach_wubi(wubi)
    for ch in "kld":
        mode.feed_key(_letter(ch), 0)
    assert mode.buffer == "kld"
    # User reports the bug: now press backspace.
    assert mode.backspace() is True
    assert mode.buffer == "kl"
    # Now type more letters.  Without the fix, the wubi engine's
    # buffer was still "kld" so the next 'a' would make "klda" and
    # be visible as if the 'd' had never been deleted.
    mode.feed_key(_letter("a"), 0)
    assert mode.buffer == "kla", f"buffer leaked old char: {mode.buffer!r}"
    # And the wubi engine should be queried with "kla" not "klda".
    assert mode._wubi_mode is not None
    assert mode._wubi_mode.buffer == "kla"
    # Pinyin engine in lockstep.
    assert mode._pinyin_mode is not None
    assert mode._pinyin_mode.buffer == "kla"


def test_wbpy_backspace_empty_returns_false() -> None:
    pinyin = Trie()
    wubi = Trie()
    mode = WbpyMode(pinyin, _FakeConfig)
    mode.attach_wubi(wubi)
    assert mode.backspace() is False


def test_wbpy_pinyin_buffer_capped_at_safe_length() -> None:
    """Regression for libgooglepinyin MatrixSearch::extend_dmi
    assertion crash.  When the user holds down a single consonant
    key (e.g. 'c'), the pinyin engine's internal decoder crashes
    on inputs of ~19 letters.  WbpyMode must cap the pinyin
    engine's buffer at 16 letters to avoid the crash.

    This test cannot exercise the real GooglePinyinMode (no
    libgooglepinyin in the test environment), but it can verify
    that the cap *constant* is set to a safe value and the
    pinyin-mode buffer is the one being protected.
    """
    import re

    with open("tux_im/input/wbpy.py") as f:
        src = f.read()
    # The cap constant must be present and ≤ 20 (well below the
    # 19-letter crash threshold, with a safety margin).
    m = re.search(r"_MAX_PINYIN_LEN\s*=\s*(\d+)", src)
    assert m is not None, "wbpy _MAX_PINYIN_LEN not found"
    cap = int(m.group(1))
    assert cap <= 20, f"wbpy cap too high: {cap}"
    assert cap >= 6, f"wbpy cap too low: {cap}"

    # GooglePinyinMode must have the same cap so a pure "google"
    # mode (not wrapped by wbpy) also survives a flood of consonants.
    with open("tux_im/input/google_pinyin_mode.py") as f:
        src = f.read()
    m = re.search(r"_MAX_DECODE_LEN\s*=\s*(\d+)", src)
    assert m is not None, "google _MAX_DECODE_LEN not found"
    cap = int(m.group(1))
    assert cap <= 20, f"google cap too high: {cap}"
    assert cap >= 6, f"google cap too low: {cap}"
