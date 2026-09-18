"""Tests for the Pinyin input mode."""

from __future__ import annotations

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus

from tux_im.input.pinyin import PinyinMode


class _FakeConfig:
    class Ime:
        max_candidates = 9

    # Re-expose under lowercase to mirror the production Config dot-path.
    ime = Ime


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


def test_punctuation_maps_to_chinese() -> None:
    """Every ASCII punctuation key that has a Chinese equivalent must be
    consumed by feed_key and committed as the Chinese character, not the
    raw ASCII.  This is the most user-visible feature of Chinese-mode
    typing — failing it (e.g. `/` falling through to return None) makes
    the IME feel broken.

    Mirrors rime-prelude/punctuation.yaml full_shape (Rime librime
    default table) so this engine feels like a familiar Rime/FCITX5
    setup.
    """
    from tux_im.input.lexicon import Trie

    trie = Trie()
    mode = PinyinMode(trie, _FakeConfig)
    pairs = [
        ("period", "。"),
        ("comma", "，"),
        ("semicolon", "；"),
        ("colon", "："),
        ("question", "？"),
        ("exclam", "！"),
        ("less", "《"),
        ("greater", "》"),
        ("parenleft", "（"),
        ("parenright", "）"),
        ("bracketleft", "「"),
        ("bracketright", "」"),
        ("braceleft", "｛"),
        ("braceright", "｝"),
        ("minus", "－"),     # fullwidth hyphen-minus (not em-dash)
        ("plus", "＋"),
        ("equal", "＝"),
        ("apostrophe", "\u2019"),
        ("quotedbl", "\u201d"),
        ("slash", "／"),     # fullwidth slash (Rime first candidate)
        ("backslash", "、"),  # Chinese enumeration comma
        ("bar", "｜"),
        ("grave", "｀"),
        ("asciitilde", "～"),
        ("at", "＠"),
        ("numbersign", "＃"),
        ("dollar", "￥"),
        ("percent", "％"),
        ("asciicircum", "……"),
        ("ampersand", "＆"),
        ("asterisk", "＊"),
    ]
    for keysym_name, expected in pairs:
        # Reset between cases so previous commits don't accumulate.
        mode.reset()
        kv = IBus.keyval_from_name(keysym_name)
        r = mode.feed_key(kv, 0)
        assert r is not None, f"{keysym_name}: feed_key returned None"
        assert r.handled, f"{keysym_name}: not handled"
        assert r.commit == expected, (
            f"{keysym_name}: expected {expected!r}, got {r.commit!r}"
        )


def test_punctuation_commits_buffer_first() -> None:
    """Typing pinyin then punctuation commits the top candidate AND emits
    the Chinese punctuation in one shot, e.g. `wo.` -> 我。"""
    from tux_im.input.lexicon import Trie

    trie = Trie()
    trie.insert("wo3", "我", 100)
    mode = PinyinMode(trie, _FakeConfig)
    mode.feed_key(_letter("w"), 0)
    mode.feed_key(_letter("o"), 0)
    mode.feed_key(_digit("3"), 0)
    assert mode.buffer == "wo3"
    r = mode.feed_key(IBus.keyval_from_name("period"), 0)
    assert r.handled
    # Top candidate ("我") + Chinese period ("。") = "我。"
    assert r.commit == "我。"
    # Pinyin mode resets its own buffer before returning so the engine
    # does not need to (clear=False); verify directly.
    assert mode.buffer == ""


def test_punctuation_with_empty_buffer_emits_only_punct() -> None:
    """When there's no pending pinyin, pressing any ASCII punctuation key
    directly emits its Chinese/fullwidth equivalent without committing
    any candidate.

    Regression: previously only the original 6 punctuation keys were
    handled; anything else fell through to feed_key's `return None` and
    was passed straight to the focused application.  After the fix
    (Rime-style full-shape table), all 28 entries in `_ASCII_TO_CHINESE`
    are mapped.
    """
    from tux_im.input.lexicon import Trie

    trie = Trie()
    mode = PinyinMode(trie, _FakeConfig)
    sample = [
        "period", "comma", "semicolon", "colon", "question", "exclam",
        "less", "greater", "parenleft", "parenright",
        "bracketleft", "bracketright",
        "minus", "plus", "equal", "slash", "backslash",
        "at", "numbersign", "dollar", "percent", "ampersand", "asterisk",
        "asciitilde", "bar", "grave", "asciicircum",
        "apostrophe", "quotedbl",
    ]
    for keysym in sample:
        mode.reset()
        assert mode.buffer == "", f"buffer should be empty before {keysym}"
        r = mode.feed_key(IBus.keyval_from_name(keysym), 0)
        assert r is not None, f"{keysym}: feed_key returned None"
        assert r.handled, f"{keysym}: not handled"
        # Commit must be a Chinese char, not the raw ASCII.  The exact
        # target is defined by _ASCII_TO_CHINESE_KEYSYM in google_pinyin_mode
        # (same source for wbpy).
        from tux_im.input.google_pinyin_mode import _ASCII_TO_CHINESE_KEYSYM
        expected = _ASCII_TO_CHINESE_KEYSYM[keysym]
        assert r.commit == expected, (
            f"{keysym}: expected {expected!r}, got {r.commit!r}"
        )
