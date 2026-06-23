"""Wubi 86 input mode."""

from __future__ import annotations

import logging
from typing import Optional

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus  # noqa: E402

from tux_im.input.base import Candidate, InputMode, KeyResult
from tux_im.input.lexicon import LexEntry, Trie

log = logging.getLogger(__name__)

_WUBI_KEYS = set("abcdefghijklmnopqrstuvwxyz")
_MAX_WUBI_LEN = 4  # standard Wubi 86 codes are 1-4 letters


class WubiMode:
    """Buffers Wubi 86 codes (1-4 letters) and looks up candidates in `WubiTrie`."""

    name = "wubi"
    buffer: str
    cursor: int

    def __init__(self, trie: Trie, config: object) -> None:
        self._trie = trie
        self._config = config
        self.buffer = ""
        self.cursor = 0
        self._page_offset = 0

    def reset(self) -> None:
        self.buffer = ""
        self.cursor = 0
        self._page_offset = 0

    def feed_key(self, keyval: int, state: int) -> Optional[KeyResult]:
        key = IBus.keyval_name(keyval)
        if key is None:
            return None
        ch = key.lower()
        if len(ch) != 1 or ch not in _WUBI_KEYS or len(self.buffer) >= _MAX_WUBI_LEN:
            return None
        # Check whether the buffer (after appending) is at least a prefix of
        # some wubi code. If not -- and especially if we have no buffer at all
        # yet -- this key would never resolve to a candidate, so return
        # handled=False to let it pass through to the app as a plain letter.
        new_buf = self.buffer + ch
        if not self._trie.has_prefix(new_buf):
            return None
        self.buffer = new_buf
        self.cursor = len(self.buffer)
        return KeyResult(handled=True)

    def candidates(self, limit: int = 9) -> list[Candidate]:
        if not self.buffer:
            return []
        entries = self._trie.lookup(self.buffer)
        cands = [Candidate(text=e.word, display=e.word, comment=e.code, freq=e.freq)
                 for e in entries]
        return cands[self._page_offset : self._page_offset + limit]

    def select(self, index: int) -> KeyResult:
        # Grab all candidates and apply _page_offset so second-page
        # selections (e.g. key "1" when on page 2) land on the right entry.
        all_cands = self.candidates(limit=9999)
        pos = self._page_offset + index
        if 0 <= pos < len(all_cands):
            return KeyResult(handled=True, commit=all_cands[pos].text, clear=True)
        return KeyResult(handled=False)

    def page(self, direction: int) -> KeyResult:
        self._page_offset = max(0, self._page_offset + direction * 9)
        return KeyResult(handled=True)

    def full_sentence(self) -> None:
        """No sentence-level decoding."""
        return None

    def commit(self) -> Optional[str]:
        if not self.buffer:
            return None
        entries = self._trie.lookup(self.buffer)
        if entries:
            return entries[0].word
        # Last resort: commit the raw wubi code so the user doesn't lose input.
        return self.buffer
