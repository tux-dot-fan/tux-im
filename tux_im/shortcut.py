"""Shortcut (hotkey) manager."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus  # noqa: E402

from tux_im.config.config import Config

log = logging.getLogger(__name__)


@dataclass
class ParsedShortcut:
    modifiers: int  # IBus.ModifierType bitmask
    keyval: int
    alt_keyval: int = 0  # Optional second keyval (e.g. opposite-case letter)

    def matches(self, keyval: int, state: int) -> bool:
        # Mask out lock keys (CapsLock, NumLock).
        relevant = state & IBus.ModifierType(
            IBus.ModifierType.CONTROL_MASK
            | IBus.ModifierType.SHIFT_MASK
            | IBus.ModifierType.MOD1_MASK
            | IBus.ModifierType.SUPER_MASK
            | IBus.ModifierType.HYPER_MASK
        )
        if self.modifiers != relevant:
            return False
        return keyval == self.keyval or (
            self.alt_keyval != 0 and keyval == self.alt_keyval
        )


def parse_shortcut(spec: str) -> ParsedShortcut:
    """Parse a GTK accelerator-style spec, e.g. '<Ctrl>grave', 'Caps_Lock'.

    Spec grammar: zero or more ``<Modifier>`` groups followed by a key name.
    Modifiers may appear in any order. Examples that parse identically:
        ``<Ctrl><Shift>m``  ``<Shift><Ctrl>m``  ``<Ctrl>m``  ``m``.

    The keyval is looked up with the original case AND with the opposite case
    so that ``<Ctrl><Shift>m`` matches both 'm' (77, the shifted keyval when
    Shift is held) and 'm' (109, the unshifted keyval) -- but only when the
    corresponding Shift modifier is also pressed.
    """
    import re

    spec = spec.strip()
    if not spec:
        raise ValueError("empty shortcut spec")

    mod_pat = re.compile(r"<([^>]+)>")
    mods = 0
    pos = 0
    for m in mod_pat.finditer(spec):
        token = m.group(1).strip().lower()
        if token in ("ctrl", "control"):
            mods |= IBus.ModifierType.CONTROL_MASK
        elif token == "shift":
            mods |= IBus.ModifierType.SHIFT_MASK
        elif token in ("alt", "mod1"):
            mods |= IBus.ModifierType.MOD1_MASK
        elif token in ("super", "win", "meta"):
            mods |= IBus.ModifierType.SUPER_MASK
        else:
            raise ValueError(f"unknown modifier {token!r} in {spec!r}")
        pos = m.end()

    keyname = spec[pos:].strip()
    if not keyname:
        raise ValueError(f"no key in shortcut: {spec!r}")

    if keyname.lower() == "space":
        keyname = "space"

    # Look up the keyval using both the original and the swapped-case name so
    # the binding matches regardless of how Shift is reported in the state.
    primary = IBus.keyval_from_name(keyname)
    if primary == 0:
        raise ValueError(f"unknown key name: {keyname!r}")

    # IBus returns 0xffffff for invalid key names that aren't actual keysyms.
    # Validate by round-trip: the round-tripped name must match the input.
    # (IBus.keyval_from_name returns 0xffffff for garbage, which round-trips to "0xffffff")
    if IBus.keyval_name(primary) != keyname:
        raise ValueError(f"unknown key name: {keyname!r}")

    # Swap-case secondary: for alpha keys, also match the opposite shift state.
    secondary = 0
    if keyname.isalpha() and len(keyname) == 1:
        swapped = IBus.keyval_from_name(keyname.swapcase())
        if swapped != 0:
            secondary = swapped

    return ParsedShortcut(mods, primary, secondary)


class ShortcutManager:
    """Translates key events into named actions via `Config.shortcuts`."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._bindings: list[tuple[ParsedShortcut, str]] = []
        self._handlers: dict[str, Callable[..., bool]] = {}
        self.rebuild()

    def register(self, action: str, handler: Callable[..., bool]) -> None:
        """Register a handler for a named shortcut action."""
        self._handlers[action] = handler

    def unregister(self, action: str) -> None:
        """Remove the handler for `action`. Silently succeeds if not registered."""
        self._handlers.pop(action, None)

    def reset(self) -> None:
        """Remove all registered handlers. Used on engine disable."""
        self._handlers.clear()

    def _call_handler(self, action: str, engine: object) -> bool:
        """Call the registered handler. Return True if the key was consumed."""
        handler = self._handlers.get(action)
        if handler is None:
            log.debug("Shortcut %s pressed but no handler", action)
            return False
        # Try passing engine first; fall back to no-arg call.
        # Both paths cast to bool so the return type is consistent.
        try:
            result = handler(engine)
        except TypeError:
            try:
                result = handler()
            except TypeError:
                log.warning("Shortcut handler %s rejected both (engine) and () calls", action)
                return False
        return bool(result)
        # NOTE: ``handler: Callable[..., bool]`` is too polymorphic for mypy to
        # statically resolve the call-site; the double try/except above is the
        # runtime-correct fallback — suppress the spurious no-untyped-call
        # report for this specific line.  # type: ignore[no-untyped-call]

    def rebuild(self) -> None:
        self._bindings.clear()
        shortcuts = self._config.shortcuts.as_dict()
        for action, spec in shortcuts.items():
            try:
                parsed = parse_shortcut(spec)
            except ValueError as exc:
                log.warning("Invalid shortcut %s=%r: %s", action, spec, exc)
                continue
            self._bindings.append((parsed, action))
        log.debug("Registered %d shortcuts", len(self._bindings))

    def handle(self, engine: object, keyval: int, state: int) -> bool:
        """Return True if the key was consumed by a shortcut."""
        # IBus sends both press and release events.  We only handle presses
        # here; the release side is filtered at the engine entry point, but
        # we also guard here so shortcut handlers are never called on RELEASE.
        if state & IBus.ModifierType.RELEASE_MASK:
            return False
        for parsed, action in self._bindings:
            if parsed.matches(keyval, state):
                log.debug("shortcut matched: action=%s keyval=%d", action, keyval)
                return self._call_handler(action, engine)
        return False
