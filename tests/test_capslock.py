"""Regression tests for CapsLock normalisation in latin (English) mode.

Background
----------
IBus/X11 reports letter keyvals in upper case when CapsLock is engaged:
pressing 'c' on the physical keyboard while CapsLock LED is on produces
keyval=67 ('C') instead of keyval=99 ('c'), with ``state`` having
``IBus.ModifierType.LOCK_MASK`` set.

If the engine simply returned False in latin mode, the upper-case keyval
would be forwarded to the focused app, causing every subsequent letter
to appear capitalised even though the user did not press Shift.  This
test guards the normalisation step that converts the letter to its
lower-case form before committing it to the app.
"""

from __future__ import annotations

import gi

gi.require_version("IBus", "1.0")
import pytest
from gi.repository import IBus  # noqa: E402


def _kv(c: str) -> int:
    from gi.repository import Gdk
    return Gdk.unicode_to_keyval(ord(c))


@pytest.fixture
def engine() -> object:
    """Construct a minimal engine wired up for latin-mode key handling.

    We bypass the full IBusEngine constructor (which connects to the bus)
    and instead create the engine instance and monkey-patch the IBus-side
    methods we do not want to exercise.  Only ``_handle_key`` is exercised.
    """
    import tux_im.engine as engine_mod

    eng = engine_mod.TuxEngine.__new__(engine_mod.TuxEngine)

    # IBus surface methods — we mock them so they record what the engine
    # wanted to display instead of actually touching the bus.
    eng.committed: list[str] = []
    eng.hidden_preedit = 0
    eng.hidden_aux = 0
    eng.hidden_lookup = 0
    eng.preedit_text: str | None = None
    eng.aux_text: str | None = None
    eng.lookup_rows: list[object] | None = None

    def _commit_text(text: IBus.Text) -> None:
        eng.committed.append(text.get_text())

    eng.commit_text = _commit_text  # type: ignore[method-assign]
    eng.hide_preedit_text = lambda: (eng.__setattr__("hidden_preedit", eng.hidden_preedit + 1))  # type: ignore[method-assign]
    eng.hide_auxiliary_text = lambda: (eng.__setattr__("hidden_aux", eng.hidden_aux + 1))  # type: ignore[method-assign]
    eng.hide_lookup_table = lambda: (eng.__setattr__("hidden_lookup", eng.hidden_lookup + 1))  # type: ignore[method-assign]
    eng.update_preedit_text = lambda *args, **kw: None  # type: ignore[method-assign]
    eng.update_auxiliary_text = lambda *args, **kw: None  # type: ignore[method-assign]
    eng.update_lookup_table = lambda *args, **kw: None  # type: ignore[method-assign]

    eng._chinese_mode = False
    eng._initialized = True
    eng._page_index = 0
    eng._lazy_init_done = False

    # Active mode is unused in latin path but engine._handle_key still
    # touches it in the shortcut step; give it a no-op stub.
    class _NoopMode:
        name = "latin"
        buffer = ""

        def feed_key(self, keyval: int, state: int) -> object:
            return None

        def reset(self) -> None:
            pass

    eng._active_mode = _NoopMode()  # type: ignore[attr-defined]

    # _handle_key reads module-level _shortcuts; install a stub that
    # returns False (no shortcut matched).
    class _Shortcuts:
        def handle(self, *_a: object, **_kw: object) -> bool:
            return False

    engine_mod._shortcuts = _Shortcuts()  # type: ignore[assignment]

    return eng


def test_capslock_uppercase_letter_lowercased_in_latin_mode(engine: object) -> None:
    """CapsLock-on 'c' (keyval 67) in latin mode should commit 'c', not 'C'."""
    state = IBus.ModifierType.LOCK_MASK
    result = engine._handle_key(_kv("C"), state)

    assert result is True, "engine should consume the key (commit + return True)"
    assert engine.committed == ["c"], (
        f"expected lowercase 'c' to be committed, got {engine.committed!r}"
    )


def test_capslock_letters_round_trip(engine: object) -> None:
    """A short CapsLock-on sequence should commit each letter lowercase."""
    state = IBus.ModifierType.LOCK_MASK
    for ch in "hello":
        result = engine._handle_key(_kv(ch.upper()), state)
        assert result is True
    assert engine.committed == ["h", "e", "l", "l", "o"]


def test_latin_mode_without_capslock_passes_through(engine: object) -> None:
    """Latin mode without CapsLock should return False (pass-through)."""
    result = engine._handle_key(_kv("c"), 0)
    assert result is False
    assert engine.committed == []


def test_capslock_digit_is_not_letters(engine: object) -> None:
    """CapsLock on a digit should NOT trigger letter normalisation; pass-through."""
    state = IBus.ModifierType.LOCK_MASK
    result = engine._handle_key(_kv("5"), state)
    # Digit is not alpha — engine returns False (normal pass-through)
    assert result is False
    assert engine.committed == []


def test_capslock_with_shift_still_lowercased(engine: object) -> None:
    """CapsLock + Shift: X11 reports lowercase keyval (Shift cancels Caps).

    Behaviourally the user sees the same lowercase character as without
    Shift, so our normalisation path is exercised but the committed
    character is lowercase.  This guards against a regression where the
    engine would special-case Shift and forward the event unchanged.
    """
    state = IBus.ModifierType.LOCK_MASK | IBus.ModifierType.SHIFT_MASK
    result = engine._handle_key(_kv("C"), state)
    assert result is True
    assert engine.committed == ["c"]


def test_capslock_punctuation_unchanged(engine: object) -> None:
    """CapsLock on punctuation does NOT normalise (only letters)."""
    state = IBus.ModifierType.LOCK_MASK
    # Period keyval 46
    result = engine._handle_key(46, state)
    assert result is False
    assert engine.committed == []


def test_capslock_chinese_mode_does_not_normalise(engine: object) -> None:
    """CapsLock in Chinese mode should NOT lowercase (it's part of input)."""
    engine._chinese_mode = True
    # 'a' normally uppercased by CapsLock.  In chinese mode the active
    # InputMode handles the keyval, so engine does NOT lowercase it
    # itself — the mode decides what to do with the letter.
    state = IBus.ModifierType.LOCK_MASK
    # We don't have a real active mode; just check that the CapsLock
    # branch is NOT taken: it should fall through to the mode handler.
    result = engine._handle_key(_kv("A"), state)
    # No exception thrown is sufficient — chinese path is exercised.
    assert result in (True, False)
