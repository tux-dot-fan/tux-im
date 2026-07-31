"""Latin mode passthrough tests.

Latin mode is activated by CapsLock; the engine short-circuits
``_handle_key`` when ``_chinese_mode`` is False and never actually
calls into ``LatinMode.feed_key``.  These tests pin the protocol
contract: even if a future refactor routes some keys into latin
mode, the mode MUST stay a pure passthrough.
"""

from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")

from gi.repository import Gdk

from tux_im.input.base import Candidate, KeyResult
from tux_im.input.latin import LatinMode


def _kv(name: str) -> int:
    """Resolve a Gdk keyval by name (e.g. 'space', 'a', 'BackSpace')."""
    keyval: int = Gdk.keyval_from_name(name)
    return keyval


def test_latin_protocol_attrs() -> None:
    mode = LatinMode(config=None)
    assert mode.name == "latin"
    assert mode.buffer == ""
    assert mode.cursor == 0


def test_latin_feed_key_returns_unhandled_for_letter() -> None:
    mode = LatinMode(config=None)
    result = mode.feed_key(_kv("a"), 0)
    assert result is not None
    assert result.handled is False
    assert result.commit is None
    assert result.clear is False


def test_latin_feed_key_passes_through_space() -> None:
    """Space must be passed through unchanged — no commit, no preediting."""
    mode = LatinMode(config=None)
    result = mode.feed_key(_kv("space"), 0)
    assert result is not None
    assert result.handled is False
    assert result.commit is None


def test_latin_feed_key_does_not_mutate_buffer() -> None:
    mode = LatinMode(config=None)
    for key in ("a", "space", "BackSpace", "Return", "semicolon"):
        mode.feed_key(_kv(key), 0)
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
    ctrl = Gdk.ModifierType.CONTROL_MASK
    for state in (ctrl, Gdk.ModifierType.ALT_MASK, Gdk.ModifierType.SUPER_MASK):
        result = mode.feed_key(_kv("a"), int(state))
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
    assert isinstance(mode.feed_key(_kv("a"), 0), KeyResult)
    assert isinstance(mode.select(0), KeyResult)
    assert isinstance(mode.page(+1), KeyResult)
