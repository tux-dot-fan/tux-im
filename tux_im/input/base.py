"""Input mode protocol and key result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass
class KeyResult:
    """Result returned by `InputMode.feed_key`.

    - `handled` -- if True, IBus consumes the key (do not pass to the app).
    - `commit` -- text to commit to the focused app, if any.
    - `clear` -- if True, the input buffer should be cleared after committing.
    """

    handled: bool = False
    commit: Optional[str] = None
    clear: bool = False


@dataclass
class Candidate:
    """A single candidate in the candidate window."""

    text: str
    display: str = ""
    comment: str = ""
    freq: int = 0

    def __post_init__(self) -> None:
        if not self.display:
            self.display = self.text


@runtime_checkable
class InputMode(Protocol):
    """Common interface for input modes."""

    name: str
    buffer: str
    cursor: int

    def feed_key(self, keyval: int, state: int) -> Optional[KeyResult]: ...
    def reset(self) -> None: ...
    def commit(self) -> Optional[str]: ...
    def candidates(self, limit: int = 9) -> list[Candidate]: ...
    def select(self, index: int) -> KeyResult: ...
    def page(self, direction: int) -> KeyResult: ...
