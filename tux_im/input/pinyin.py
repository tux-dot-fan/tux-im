"""Pinyin input mode."""

from __future__ import annotations

import logging
from typing import Optional

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus  # noqa: E402

from tux_im.input.base import Candidate, InputMode, KeyResult
from tux_im.input.lexicon import LexEntry, Trie

log = logging.getLogger(__name__)

# Pinyin input: a-z letters, then optional tone number (1-5).
_PINYIN_KEYS = set("abcdefghijklmnopqrstuvwxyz")
_TONE_KEYS = {"1", "2", "3", "4", "5"}
_PINYIN_SEPARATORS = {" ", "'"}  # space and apostrophe split pinyin syllables


class PinyinMode:
    """Buffers pinyin (with tone numbers) and looks up candidates in `PinyinTrie`."""

    name = "pinyin"
    buffer: str
    cursor: int

    def __init__(self, trie: Trie, config) -> None:
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
        log.debug("PinyinMode.feed_key: keyval=%d key=%r ch=%r buffer_before=%r",
                  keyval, key, ch, self.buffer)

        # Digit tone
        if ch in _TONE_KEYS and self.buffer and self.buffer[-1].isalpha():
            self.buffer += ch
            self.cursor = len(self.buffer)
            log.debug("PinyinMode.feed_key: tone digit, buffer=%r", self.buffer)
            return KeyResult(handled=True)

        # Letter
        if len(ch) == 1 and ch in _PINYIN_KEYS:
            self.buffer += ch
            self.cursor = len(self.buffer)
            log.debug("PinyinMode.feed_key: letter, buffer=%r", self.buffer)
            return KeyResult(handled=True)

        return None

    def candidates(self, limit: int = 9) -> list[Candidate]:
        if not self.buffer:
            return []
        entries = self._trie.lookup(self.buffer)
        cands = [_entry_to_candidate(e) for e in entries]
        return cands[self._page_offset : self._page_offset + limit]

    def select(self, index: int) -> KeyResult:
        cands = self.candidates(limit=9)
        if 0 <= index < len(cands):
            return KeyResult(handled=True, commit=cands[index].text, clear=True)
        return KeyResult(handled=False)

    def page(self, direction: int) -> KeyResult:
        self._page_offset = max(0, self._page_offset + direction * 9)
        return KeyResult(handled=True)

    def commit(self) -> Optional[str]:
        if not self.buffer:
            return None
        # First try to look up the buffer as a complete pinyin code.
        entries = self._trie.lookup(self.buffer)
        if entries:
            return entries[0].word
        # Fallback: strip trailing tone digit and try again so "ni3" → "你".
        buf = self.buffer
        if len(buf) > 1 and buf[-1].isdigit():
            entries = self._trie.lookup(buf[:-1])
            if entries:
                return entries[0].word
        # Last resort: commit the raw buffer so the user doesn't lose input.
        return self.buffer


def _entry_to_candidate(e: LexEntry) -> Candidate:
    return Candidate(text=e.word, display=e.word, comment=e.code, freq=e.freq)
