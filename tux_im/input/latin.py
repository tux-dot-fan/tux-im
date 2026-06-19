"""Latin (English) passthrough mode."""

from __future__ import annotations

from typing import Optional

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus  # noqa: E402

from tux_im.input.base import Candidate, InputMode, KeyResult


class LatinMode:
    """Passthrough mode. Returns `None` for all keys so IBus forwards them
    to the focused app unchanged."""

    name = "latin"
    buffer = ""
    cursor = 0

    def __init__(self, config) -> None:  # noqa: ARG002
        pass

    def feed_key(self, keyval: int, state: int) -> Optional[KeyResult]:  # noqa: ARG002
        return None

    def reset(self) -> None:
        pass

    def commit(self) -> Optional[str]:
        return None

    def candidates(self, limit: int = 9) -> list[Candidate]:  # noqa: ARG002
        return []

    def select(self, index: int) -> KeyResult:  # noqa: ARG002
        return KeyResult(handled=False)

    def page(self, direction: int) -> KeyResult:  # noqa: ARG002
        return KeyResult(handled=False)
