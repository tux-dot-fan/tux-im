"""Input mode protocol and key result types.

Architecture
============
The engine (engine.py) is the IBus interface layer.  It delegates all
input processing to the active InputMode.  The engine handles:

  key event (IBus)
    ↓
  shortcut check (_shortcuts.handle)
    ↓  consumed
  mode.feed_key(keyval, state)     ← input mode updates buffer / state
    ↓ Optional[KeyResult]
  mode.candidates(limit)           ← engine reads for display
    ↓
  user selects candidate i
    ↓
  mode.select(i) → KeyResult       ← engine commits text + calls reset() if clear

The mode is responsible ONLY for input processing and candidate generation.
The engine owns all IBus transport calls (commit_text, update_preedit_text,
etc.).  This separation keeps modes testable without IBus.

Key invariant: candidates()[i].text MUST equal select(i).commit.
Violations cause "phantom commits" where the user clicks the visible
candidate but a different word is inserted.  See test_engine_flow.py:
test_candidates_and_select_index_consistency().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass
class KeyResult:
    """Result returned by ``InputMode.feed_key`` and ``InputMode.select``.

    Attributes
    ----------
    handled : bool
        If True, the key was consumed by the input mode and must NOT be
        passed to the focused application.  If False, the engine will
        forward the key event to the application.
    commit : str, optional
        Text to commit to the application (i.e. insert into the text field).
        When this is set the engine calls ``commit_text()``.
    clear : bool
        If True, the engine will call ``mode.reset()`` after committing.
        The mode itself does NOT reset its buffer; that is the engine's
        responsibility so the engine can update the UI first.

    Notes
    -----
    It is valid for ``handled=False`` and ``commit`` to be set simultaneously:
    the key is passed through but text is still committed (e.g. space in
    English mode where the engine simply forwards the space character).

    ``handled=True`` with no ``commit`` means the key is consumed for IME
    purposes (e.g. a BackSpace that deleted a character).
    """

    handled: bool = False
    commit: Optional[str] = None
    clear: bool = False


@dataclass
class Candidate:
    """A single candidate shown in the lookup table.

    Attributes
    ----------
    text : str
        The actual word/character to insert if this candidate is selected.
    display : str
        What to show in the candidate window.  Defaults to ``text``.
        May include annotations (e.g. frequency rank, pinyin) but the
        displayed text is purely for human reading.
    comment : str, optional
        Extra annotation shown alongside the candidate (e.g. "ni3", "Wubi: ycfg").
    freq : int
        Internal frequency score.  Used for sorting; not shown to the user.
    """

    text: str
    display: str = ""
    comment: str = ""
    freq: int = 0

    def __post_init__(self) -> None:
        if not self.display:
            self.display = self.text


@runtime_checkable
class InputMode(Protocol):
    """Common interface for all input modes (pinyin, wubi, wbpy, latin).

    Protocol methods
    ---------------

    feed_key(keyval, state) -> Optional[KeyResult]
        Handle a key press.  ``keyval`` is a Gdk keyval (see Gdk.keysyms).
        ``state`` is the Gdk modifier state (0 for no modifiers).
        Returns None if the key is completely irrelevant to this mode
        (engine treats None as handled=False).  Returns KeyResult otherwise.

        Side effects: updates ``self.buffer``, ``self.cursor``.

    reset() -> None
        Clears ``self.buffer`` and resets ``self.cursor`` to 0.
        Called by the engine after a select() that returns clear=True,
        or when the user presses Escape.

    commit() -> Optional[str]
        Commits the top-ranked candidate for the current buffer WITHOUT
        clearing it.  Used by the engine when focus is lost (do_focus_out)
        so pending input is not silently dropped.
        Returns the committed string, or None if buffer is empty.
        NOTE: this does NOT clear the buffer; the engine does that via reset().

    candidates(limit=9) -> list[Candidate]
        Returns up to ``limit`` candidates for the current buffer.
        The returned list MUST be in the same order that select(i) will
        use for indexing.  This invariant is enforced by
        test_engine_flow.py::test_candidates_and_select_index_consistency().

        The engine calls this after every feed_key to update the lookup
        table.  May return an empty list (e.g. buffer too short for any match).

        IMPORTANT: ``candidates()`` is called AFTER feed_key returns but
        BEFORE select() is called.  Neither method should have observable
        side effects on the other (calling select() must not change the
        ordering of candidates returned by the next candidates() call).

    select(index) -> KeyResult
        Selects and commits the candidate at ``index`` in the current
        candidate list.  index 0 = first candidate shown (top-ranked).
        Returns KeyResult with commit=text, clear=True.
        Returns KeyResult(handled=False) if index is out of range.

        After a successful select(), the mode's buffer is NOT automatically
        cleared; the engine calls reset() after reading result.clear=True.

        CRITICAL INVARIANT: candidates()[index].text MUST equal select(index).commit
        for all valid index values.  Violations cause phantom commits.

    page(direction) -> KeyResult
        Advances the candidate page.  direction=+1 for next page,
        direction=-1 for previous page.  Modifies the internal page offset
        used by candidates() to slice the result list.
        Returns KeyResult(handled=True) always (page navigation is internal).

    full_sentence() -> Optional[str]
        Returns the full decoded sentence (all words, no segmentation).
        Only relevant for sentence-level decoders (e.g. Google Pinyin).
        Other modes return None.  The engine displays this in auxiliary text
        so it does not duplicate the first entry of the candidate list.

    Required instance attributes
    ----------------------------
    name : str
        Unique identifier: "pinyin", "wubi", "wbpy", or "latin".

    buffer : str
        Current user input buffer (raw keystrokes, e.g. "ni3" or "ycfg").

    cursor : int
        Current cursor position within buffer (for future bi-directional
        input support).  Currently not used by all modes but must exist.
    """

    name: str
    buffer: str
    cursor: int

    def feed_key(self, keyval: int, state: int) -> Optional[KeyResult]:
        """Handle a key press.  See class docstring for details."""
        ...

    def reset(self) -> None:
        """Clear the input buffer.  See class docstring for details."""
        ...

    def commit(self) -> Optional[str]:
        """Commit top candidate without clearing.  See class docstring for details."""
        ...

    def candidates(self, limit: int = 9) -> list[Candidate]:
        """Return candidates for the current buffer.  See class docstring for details."""
        ...

    def select(self, index: int) -> KeyResult:
        """Select candidate at index.  See class docstring for details."""
        ...

    def page(self, direction: int) -> KeyResult:
        """Navigate candidate pages.  See class docstring for details."""
        ...

    def full_sentence(self) -> Optional[str]:
        """Return full decoded sentence.  See class docstring for details."""
        ...

    def backspace(self) -> bool:
        """Delete one character from the user's input.

        Modes that maintain multiple internal buffers (e.g. wbpy, which
        keeps the wubi half and the pinyin half in sync) MUST override
        this so that deleting from the visible buffer also rolls back
        the right amount in every sub-engine.

        The default implementation in :class:`InputMode` is to chop
        ``self.buffer`` by one character — this is correct for modes
        where the visible buffer is the sole source of state
        (pinyin, wubi, google, latin, emoji).

        Returns True if a character was actually deleted, False if the
        buffer is already empty (in which case the engine will pass
        BackSpace through to the focused app).
        """
        ...
