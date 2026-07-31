"""Latin mode passthrough tests.

Latin mode is activated by CapsLock; the engine short-circuits
``_handle_key`` when ``_chinese_mode`` is False and never actually
calls into ``LatinMode.feed_key``.  These tests pin the protocol
contract: even if a future refactor routes some keys into latin
mode (e.g. for the ASR overlay keyboard hook) the mode MUST stay
a pure passthrough.

No Gdk / Gdk-4.0 dependency: this test suite uses hardcoded IBus
keyval constants instead of ``Gdk.keyval_from_name`` so it runs on
CI runners that only ship Gdk 3.  The keyval numeric values are
defined by the X11 keysyms namespace (and identical between Gdk
3 and Gdk 4), so hardcoding is safe.
"""

from __future__ import annotations

import gi

gi.require_version("IBus", "1.0")

from gi.repository import IBus

from tux_im.input.base import Candidate, KeyResult
from tux_im.input.latin import LatinMode

# Hardcoded X11 keysym values (Gdk 3 / Gdk 4 / IBus all agree on these).
KV_SPACE = 32           # XK_space
KV_A = 97               # XK_a
KV_BACKSPACE = 65288    # XK_BackSpace
KV_RETURN = 65293       # XK_Return
KV_SEMICOLON = 59       # XK_semicolon
# IBus modifier mask values (stable across versions).
MASK_CONTROL = int(IBus.ModifierType.CONTROL_MASK)
MASK_ALT = int(IBus.ModifierType.MOD1_MASK)
MASK_SUPER = int(IBus.ModifierType.SUPER_MASK)


def test_latin_protocol_attrs() -> None:
    mode = LatinMode(config=None)
    assert mode.name == "latin"
    assert mode.buffer == ""
    assert mode.cursor == 0


def test_latin_feed_key_returns_unhandled_for_letter() -> None:
    mode = LatinMode(config=None)
    result = mode.feed_key(KV_A, 0)
    assert result is not None
    assert result.handled is False
    assert result.commit is None
    assert result.clear is False


def test_latin_feed_key_passes_through_space() -> None:
    """Space must be passed through unchanged — no commit, no preediting."""
    mode = LatinMode(config=None)
    result = mode.feed_key(KV_SPACE, 0)
    assert result is not None
    assert result.handled is False
    assert result.commit is None


def test_latin_feed_key_does_not_mutate_buffer() -> None:
    mode = LatinMode(config=None)
    for key in (KV_A, KV_SPACE, KV_BACKSPACE, KV_RETURN, KV_SEMICOLON):
        mode.feed_key(key, 0)
    assert mode.buffer == ""
    assert mode.cursor == 0


def test_latin_commit_returns_none() -> None:
    """focus-out must not commit anything in latin mode."""
    mode = LatinMode(config=None)
    assert mode.commit() is None


def test_latin_candidates_empty() -> None:
    mode = LatinMode(config=None)
    assert mode.candidates(limit=9) == []
    assert mode.candidates(limit=1) == []
    assert mode.candidates(limit=0) == []


def test_latin_select_out_of_range() -> None:
    mode = LatinMode(config=None)
    result = mode.select(0)
    assert result.handled is False
    assert result.commit is None


def test_latin_page_is_noop() -> None:
    mode = LatinMode(config=None)
    assert mode.page(+1).handled is False
    assert mode.page(-1).handled is False


def test_latin_backspace_returns_false_so_engine_passes_through() -> None:
    """BackSpace in latin mode falls through to the focused app."""
    mode = LatinMode(config=None)
    assert mode.backspace() is False


def test_latin_full_sentence_returns_none() -> None:
    mode = LatinMode(config=None)
    result: str | None = mode.full_sentence()
    assert result is None


def test_latin_reset_is_idempotent() -> None:
    mode = LatinMode(config=None)
    mode.reset()
    mode.reset()
    assert mode.buffer == ""
    assert mode.cursor == 0


def test_latin_satisfies_input_mode_protocol() -> None:
    """Runtime check: LatinMode must quack like an InputMode."""
    from tux_im.input.base import InputMode

    mode = LatinMode(config=None)
    assert isinstance(mode, InputMode)


def test_latin_does_not_swallow_modifiers() -> None:
    """With Ctrl/Alt/Super held, latin mode still reports handled=False."""
    mode = LatinMode(config=None)
    for state in (MASK_CONTROL, MASK_ALT, MASK_SUPER):
        result = mode.feed_key(KV_A, state)
        assert result is not None
        assert result.handled is False


def test_latin_candidates_type_is_list_of_candidate() -> None:
    """candidates() return type matches the protocol even when empty."""
    mode = LatinMode(config=None)
    result = mode.candidates(limit=5)
    assert isinstance(result, list)
    assert all(isinstance(c, Candidate) for c in result)


def test_latin_key_result_typed_correctly() -> None:
    """Each protocol method must return the exact documented type."""
    mode = LatinMode(config=None)
    assert isinstance(mode.feed_key(KV_A, 0), KeyResult)
    assert isinstance(mode.select(0), KeyResult)
    assert isinstance(mode.page(+1), KeyResult)
