"""Shortcut (hotkey) manager."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus  # noqa: E402

from tux_im.config.config import Config

log = logging.getLogger(__name__)


@dataclass
class ParsedShortcut:
    modifiers: int  # IBus.ModifierType bitmask
    keyval: int

    def matches(self, keyval: int, state: int) -> bool:
        # Mask out lock keys (CapsLock, NumLock).
        relevant = state & IBus.ModifierType(
            IBus.ModifierType.CONTROL_MASK
            | IBus.ModifierType.SHIFT_MASK
            | IBus.ModifierType.MOD1_MASK
            | IBus.ModifierType.SUPER_MASK
            | IBus.ModifierType.HYPER_MASK
        )
        return self.keyval == keyval and (self.modifiers == relevant)


def parse_shortcut(spec: str) -> ParsedShortcut:
    """Parse a GTK accelerator-style spec, e.g. '<Ctrl>grave', 'Caps_Lock'."""
    spec = spec.strip()
    if not spec:
        raise ValueError("empty shortcut spec")

    parts = spec.replace(">", "><").strip("<>").split("><")
    mods = 0
    keys: list[str] = []
    for p in parts:
        pl = p.lower()
        if pl in ("ctrl", "control"):
            mods |= IBus.ModifierType.CONTROL_MASK
        elif pl in ("shift",):
            mods |= IBus.ModifierType.SHIFT_MASK
        elif pl in ("alt", "mod1"):
            mods |= IBus.ModifierType.MOD1_MASK
        elif pl in ("super", "win", "meta"):
            mods |= IBus.ModifierType.SUPER_MASK
        else:
            keys.append(p)

    if not keys:
        raise ValueError(f"no key in shortcut: {spec!r}")

    # Use last non-modifier token as the key.
    keyname = keys[-1]
    if keyname.lower() == "space":
        keyname = "space"
    keyval = IBus.keyval_from_name(keyname)
    if keyval == 0:
        raise ValueError(f"unknown key name: {keyname!r}")

    return ParsedShortcut(mods, keyval)


class ShortcutManager:
    """Translates key events into named actions via `Config.shortcuts`."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._bindings: list[tuple[ParsedShortcut, str]] = []
        self._handlers: dict[str, Callable] = {}
        self.rebuild()

    def register(self, action: str, handler: Callable) -> None:
        """Register a handler for a named shortcut action."""
        self._handlers[action] = handler

    def _call_handler(self, action: str, engine) -> bool:
        """Call the registered handler. Return True if the key was consumed."""
        handler = self._handlers.get(action)
        if handler is None:
            log.debug("Shortcut %s pressed but no handler", action)
            return False
        # Handlers may take (engine) or no args; they may return True/False to
        # indicate whether they actually consumed the key.
        for call in (lambda: handler(engine), lambda: handler()):
            try:
                return bool(call())
            except TypeError:
                continue
        return True

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

    def handle(self, engine, keyval: int, state: int) -> bool:
        """Return True if the key was consumed by a shortcut."""
        if state & IBus.ModifierType.RELEASE_MASK:
            return False
        for parsed, action in self._bindings:
            if parsed.matches(keyval, state):
                return self._call_handler(action, engine)
        return False
