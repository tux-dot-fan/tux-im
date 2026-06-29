"""Regression tests for modifier-key passthrough to the application.

Background
----------
IBus forwards every key press to the IME engine first; the engine returns
True ("I consumed it") or False ("hand it back to the app").  When the
engine returns True, the application never sees the key.

Before the fix, every InputMode (PinyinMode, GooglePinyinMode, WbpyMode)
treated Ctrl-/Alt-/Super-modified letters as bare letters:

    Ctrl-C    -> keyval 'c' (99), state CONTROL_MASK
                 PinyinMode: ch='c', len(ch)==1, in _PINYIN_KEYS
                 -> append 'c' to pinyin buffer

That silently broke every application shortcut that happened to involve
a letter: Ctrl-C (copy / SIGINT), Ctrl-V (paste), Ctrl-X (cut),
Ctrl-Z (undo), Ctrl-A (select all), Ctrl-S (save), Ctrl-F (find), ...

The fix lives in Engine._handle_key step 3: keys with CONTROL_MASK,
MOD1_MASK, SUPER_MASK or HYPER_MASK short-circuit *after* the
shortcut manager but *before* the InputMode.  This matches the
behaviour of fcitx5 and ibus-libpinyin.

Shift is INTENTIONALLY NOT in the guard: shifted letters (e.g. Shift+c
-> 'C') are legitimate pinyin input, not application shortcuts.
"""

from __future__ import annotations

import gi

gi.require_version("IBus", "1.0")
import pytest
from gi.repository import IBus


def _kv(c: str) -> int:
    from gi.repository import Gdk
    return Gdk.unicode_to_keyval(ord(c))


class _RecordingMode:
    """InputMode stub that records every key it sees.

    Returns handled=True so we can tell apart 'feed_key was called' from
    'the key never reached the mode' (engine returns False).
    """

    name = "recording"

    def __init__(self) -> None:
        self.buffer = ""
        self.reset_calls = 0
        self.feed_calls: list[tuple[int, int]] = []  # (keyval, state)

    def feed_key(self, keyval: int, state: int) -> object:
        self.feed_calls.append((keyval, state))
        return None  # engine treats None as "not handled", returns False

    def reset(self) -> None:
        self.reset_calls += 1
        self.buffer = ""


@pytest.fixture
def engine() -> object:
    """Build a minimal engine in chinese mode with a recording InputMode.

    We bypass the IBus bus (no real connection) and stub out the surface
    methods (commit_text, update_*_text, etc.) so the engine can run
    _handle_key in isolation.  Only _handle_key is exercised.
    """
    import tux_im.engine as engine_mod

    eng = engine_mod.TuxEngine.__new__(engine_mod.TuxEngine)

    # Surface stubs.
    eng.committed: list[str] = []
    eng.preedit_text: str | None = None
    eng.aux_text: str | None = None
    eng.lookup_rows: list[object] | None = None

    eng.commit_text = lambda text: eng.committed.append(text.get_text())  # type: ignore[method-assign]
    eng.update_preedit_text = lambda *a, **kw: None  # type: ignore[method-assign]
    eng.update_auxiliary_text = lambda *a, **kw: None  # type: ignore[method-assign]
    eng.update_lookup_table = lambda *a, **kw: None  # type: ignore[method-assign]
    eng._refresh_preedit = lambda: None  # type: ignore[method-assign]

    eng._chinese_mode = True
    eng._initialized = True
    eng._page_index = 0

    eng._active_mode = _RecordingMode()  # type: ignore[attr-defined]

    class _Shortcuts:
        """No-op shortcut manager (returns False for everything)."""

        def handle(self, *_a: object, **_kw: object) -> bool:
            return False

    engine_mod._shortcuts = _Shortcuts()  # type: ignore[assignment]

    return eng


# ---------------------------------------------------------------------------
# The bug: Ctrl-letter must reach the application, not the InputMode.
# ---------------------------------------------------------------------------


def test_ctrl_letter_passes_through_in_chinese_mode(engine: object) -> None:
    """Ctrl-C in chinese mode must return False and never reach the InputMode."""
    state = IBus.ModifierType.CONTROL_MASK
    result = engine._handle_key(_kv("c"), state)
    assert result is False, "Ctrl-C must pass through to the app"
    mode = engine._active_mode  # type: ignore[attr-defined]
    assert mode.feed_calls == [], (
        f"InputMode was called for Ctrl-C; recorded {mode.feed_calls}"
    )


def test_ctrl_full_alphabet_passes_through(engine: object) -> None:
    """All Ctrl-Letter combos must pass through; none reach the InputMode."""
    for ch in "abcdefghijklmnopqrstuvwxyz":
        engine._active_mode.feed_calls.clear()  # type: ignore[attr-defined]
        result = engine._handle_key(_kv(ch), IBus.ModifierType.CONTROL_MASK)
        assert result is False, f"Ctrl-{ch.upper()} must pass through"
        mode = engine._active_mode  # type: ignore[attr-defined]
        assert mode.feed_calls == [], (
            f"InputMode ate Ctrl-{ch.upper()}: {mode.feed_calls}"
        )


def test_ctrl_v_passes_through(engine: object) -> None:
    """Specifically: Ctrl-V (paste) must not pollute the pinyin buffer."""
    engine._active_mode.buffer = "ni"  # type: ignore[attr-defined]
    result = engine._handle_key(_kv("v"), IBus.ModifierType.CONTROL_MASK)
    assert result is False
    mode = engine._active_mode  # type: ignore[attr-defined]
    assert mode.feed_calls == []
    assert mode.buffer == ""  # composition discarded on Ctrl-letter
    assert mode.reset_calls == 1, "buffer should have been reset"


def test_ctrl_letter_discards_in_progress_composition(engine: object) -> None:
    """User types "ni" (pinyin buffer=ni), then hits Ctrl-X.

    The 'X' must NOT extend the buffer to 'nix', and the in-progress
    composition must be discarded (matches fcitx5 / ibus-libpinyin
    behaviour).  The app then sees only the Ctrl-X.
    """
    engine._active_mode.buffer = "ni"  # type: ignore[attr-defined]
    state = IBus.ModifierType.CONTROL_MASK
    result = engine._handle_key(_kv("x"), state)
    assert result is False
    mode = engine._active_mode  # type: ignore[attr-defined]
    assert mode.feed_calls == [], "Ctrl-X must not reach the InputMode"
    assert mode.buffer == "", "in-progress composition must be discarded"
    assert mode.reset_calls == 1


# ---------------------------------------------------------------------------
# Other modifiers: Alt, Super, Hyper also belong to the app.
# ---------------------------------------------------------------------------


def test_alt_letter_passes_through(engine: object) -> None:
    """Alt-letter combos (e.g. Alt-F to open the File menu) must pass through."""
    state = IBus.ModifierType.MOD1_MASK
    result = engine._handle_key(_kv("f"), state)
    assert result is False
    mode = engine._active_mode  # type: ignore[attr-defined]
    assert mode.feed_calls == []


def test_super_letter_passes_through(engine: object) -> None:
    """Super (Win/Cmd) + letter must pass through."""
    state = IBus.ModifierType.SUPER_MASK
    result = engine._handle_key(_kv("e"), state)
    assert result is False
    mode = engine._active_mode  # type: ignore[attr-defined]
    assert mode.feed_calls == []


def test_hyper_letter_passes_through(engine: object) -> None:
    """Hyper (rare, but defined by X11) + letter must pass through."""
    state = IBus.ModifierType.HYPER_MASK
    result = engine._handle_key(_kv("a"), state)
    assert result is False
    mode = engine._active_mode  # type: ignore[attr-defined]
    assert mode.feed_calls == []


def test_ctrl_alt_combination_passes_through(engine: object) -> None:
    """Ctrl+Alt+letter (common Linux shortcut) must pass through."""
    state = (
        IBus.ModifierType.CONTROL_MASK | IBus.ModifierType.MOD1_MASK
    )
    result = engine._handle_key(_kv("t"), state)
    assert result is False
    mode = engine._active_mode  # type: ignore[attr-defined]
    assert mode.feed_calls == []


# ---------------------------------------------------------------------------
# Shift must NOT short-circuit: shifted letters are legitimate pinyin.
# ---------------------------------------------------------------------------


def test_shift_letter_reaches_input_mode(engine: object) -> None:
    """Shift+c (uppercase C) is a legitimate pinyin letter, NOT a shortcut.

    Shift is intentionally not in the guard.  This test guards against
    a regression where someone 'be safe' adds Shift to the mask.
    """
    state = IBus.ModifierType.SHIFT_MASK
    result = engine._handle_key(_kv("c"), state)
    mode = engine._active_mode  # type: ignore[attr-defined]
    assert mode.feed_calls == [(99, state)], (
        f"Shift+C must reach InputMode; got {mode.feed_calls}"
    )


def test_plain_letter_reaches_input_mode(engine: object) -> None:
    """Bare letter (no modifier) reaches InputMode as before.  Sanity check."""
    result = engine._handle_key(_kv("n"), 0)
    mode = engine._active_mode  # type: ignore[attr-defined]
    assert mode.feed_calls == [(_kv("n"), 0)]


def test_bare_punctuation_reaches_input_mode(engine: object) -> None:
    """Bare punctuation reaches InputMode (committed via PinyinMode path)."""
    kv_period = IBus.keyval_from_name("period")
    result = engine._handle_key(kv_period, 0)
    mode = engine._active_mode  # type: ignore[attr-defined]
    assert mode.feed_calls == [(kv_period, 0)]


# ---------------------------------------------------------------------------
# Latin mode: Ctrl-letter was already passing through before the fix;
# this test guards against the fix accidentally regressing it.
# ---------------------------------------------------------------------------


def test_ctrl_letter_passes_through_in_latin_mode(engine: object) -> None:
    engine._chinese_mode = False
    state = IBus.ModifierType.CONTROL_MASK
    result = engine._handle_key(_kv("c"), state)
    assert result is False
    mode = engine._active_mode  # type: ignore[attr-defined]
    assert mode.feed_calls == []


# ---------------------------------------------------------------------------
# Shortcut manager priority: user-configured shortcuts beat the modifier guard.
# ---------------------------------------------------------------------------


def test_user_shortcut_still_consumed(engine: object) -> None:
    """If the user has bound Ctrl-Space to something, it must STILL be consumed
    -- the shortcut manager runs BEFORE the modifier guard.
    """
    import tux_im.engine as engine_mod

    consumed: list[tuple[int, int]] = []

    class _StubShortcuts:
        def handle(self, engine_obj: object, keyval: int, state: int) -> bool:
            consumed.append((keyval, state))
            return True  # pretend we matched a user shortcut

    engine_mod._shortcuts = _StubShortcuts()  # type: ignore[assignment]

    result = engine._handle_key(
        IBus.keyval_from_name("space"),
        IBus.ModifierType.CONTROL_MASK,
    )
    assert result is True, "shortcut manager must consume the key first"
    assert consumed == [(IBus.keyval_from_name("space"), IBus.ModifierType.CONTROL_MASK)]
    mode = engine._active_mode  # type: ignore[attr-defined]
    assert mode.feed_calls == [], "InputMode must NOT see a consumed shortcut"


# ---------------------------------------------------------------------------
# Regression detail: a Ctrl-letter arrives with a non-zero keyval/state.
# ---------------------------------------------------------------------------


def test_ctrl_letter_does_not_pollute_buffer_with_letter(engine: object) -> None:
    """Specifically guard the visible symptom: typing 'c' (no Ctrl) must
    reach the InputMode, but Ctrl-C must not.  If this test ever fails
    the way it did before the fix, the user's pinyin buffer would have
    contained 'c' after pressing Ctrl-C.
    """
    engine._active_mode.buffer = ""  # type: ignore[attr-defined]

    # Plain 'c': should reach InputMode (record).
    engine._handle_key(_kv("c"), 0)
    assert len(engine._active_mode.feed_calls) == 1  # type: ignore[attr-defined]

    # Reset, then Ctrl-C: must NOT reach InputMode.
    engine._active_mode.feed_calls.clear()  # type: ignore[attr-defined]
    engine._handle_key(_kv("c"), IBus.ModifierType.CONTROL_MASK)
    assert engine._active_mode.feed_calls == []  # type: ignore[attr-defined]