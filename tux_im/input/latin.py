"""Latin (English) passthrough mode.

In Latin mode the IME acts as a pure pass-through: every keypress is
forwarded to the application without any preediting, candidates, or
conversion.  This is used when the user presses Caps-Lock to temporarily
suspend Chinese input.
"""

from __future__ import annotations

from typing import Optional

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus  # noqa: E402

from tux_im.input.base import Candidate, InputMode, KeyResult


class LatinMode:
    """Passthrough mode — all keys are forwarded to the application unchanged.

    This mode is activated by Caps-Lock (toggle_en_cn).  The engine's
    _handle_key already returns False when _chinese_mode is False, so Latin
    mode itself does not need to do any character processing; it only needs
    to implement the InputMode protocol without crashing.
    """

    name = "latin"
    buffer = ""
    cursor = 0

    def __init__(self, config: object) -> None:
        pass

    def feed_key(self, keyval: int, state: int) -> Optional[KeyResult]:
        # Engine._handle_key returns False immediately when _chinese_mode is
        # False (line: "if not self._chinese_mode: return False"), so Latin
        # mode never actually receives a key event in normal operation.
        # Still, return a definitive KeyResult so the protocol is explicit.
        return KeyResult(handled=False)

    def reset(self) -> None:
        pass

    def commit(self) -> Optional[str]:
        return None

    def candidates(self, limit: int = 9) -> list[Candidate]:
        return []

    def select(self, index: int) -> KeyResult:
        return KeyResult(handled=False)

    def page(self, direction: int) -> KeyResult:
        return KeyResult(handled=False)
