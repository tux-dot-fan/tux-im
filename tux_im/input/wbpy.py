"""Wbpy (mixed Wubi + Pinyin) input mode.

Algorithm:
- Wubi codes are 1-4 letters.
- Pinyin codes are 1-6 letters, optionally with a trailing tone digit 1-5.
- The first key of a wubi code is strongly biased: certain letters are
  extremely common first keys (g, h, k, l, m, n, t, y, ...).  Pinyin syllables
  start from a much wider letter distribution.
- Disambiguation rule: if the current buffer (no tone digit) is exactly a
  Wubi prefix and the wubi trie has a 1-char match that is not also a
  common pinyin initial, prefer Wubi.  Otherwise, prefer Pinyin.  Both
  candidate lists are merged with Wubi entries shown first.
"""

from __future__ import annotations

import logging
from typing import Optional

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus  # noqa: E402

from tux_im.input.base import Candidate, InputMode, KeyResult
from tux_im.input.lexicon import LexEntry, Trie
from tux_im.input.pinyin import PinyinMode
from tux_im.input.wubi import WubiMode

log = logging.getLogger(__name__)

# Letters that are *very* common as Wubi first keys.  Used to bias
# the heuristic: if the buffer ends in a wubi code and starts with one
# of these, treat as Wubi.
_WUBI_FIRST_KEY_HINTS = set("ghklmnotvy")


class WbpyMode:
    """Mixed mode. Wraps a `PinyinMode` and a `WubiMode` and merges their
    candidates, with the buffer interpreted as either scheme depending on
    the current contents."""

    name = "wbpy"
    buffer: str
    cursor: int

    def __init__(self, pinyin_trie: Trie, config) -> None:
        self._pinyin_mode = PinyinMode(pinyin_trie, config)
        # We share the wubi trie via a closure: the lexicon passes pinyin trie,
        # but the constructor also needs the wubi trie.  Wbpy is created with
        # a single trie arg from the engine; in practice the engine passes the
        # pinyin trie.  We accept a wubi trie via attribute injection in engine.
        self._wubi_mode: WubiMode | None = None
        self._config = config
        self.buffer = ""
        self.cursor = 0
        self._page_offset = 0

    def attach_wubi(self, wubi_trie: Trie) -> None:
        """Inject the Wubi trie after construction (engine wires this up)."""
        self._wubi_mode = WubiMode(wubi_trie, self._config)

    def reset(self) -> None:
        self.buffer = ""
        self.cursor = 0
        self._page_offset = 0
        self._pinyin_mode.reset()
        if self._wubi_mode:
            self._wubi_mode.reset()

    def feed_key(self, keyval: int, state: int) -> Optional[KeyResult]:
        key = IBus.keyval_name(keyval)
        if key is None:
            return None
        ch = key.lower()
        if len(ch) != 1 or not ch.isalpha():
            return None

        # Determine likely mode based on the current buffer.
        if self._looks_like_wubi(self.buffer) and self._wubi_mode:
            self._wubi_mode.buffer = self.buffer
            res = self._wubi_mode.feed_key(keyval, state)
            if res and res.handled:
                self.buffer = self._wubi_mode.buffer
                self.cursor = len(self.buffer)
                return res
            # Fall through to pinyin if wubi rejected (e.g. > 4 chars).
        if self._looks_like_pinyin(self.buffer):
            self._pinyin_mode.buffer = self.buffer
            res = self._pinyin_mode.feed_key(keyval, state)
            if res and res.handled:
                self.buffer = self._pinyin_mode.buffer
                self.cursor = len(self.buffer)
                return res
        return None

    def candidates(self, limit: int = 9) -> list[Candidate]:
        if not self.buffer:
            return []
        wubi_cands: list[Candidate] = []
        pinyin_cands: list[Candidate] = []
        if self._wubi_mode and self._looks_like_wubi(self.buffer):
            self._wubi_mode.buffer = self.buffer
            wubi_cands = self._wubi_mode.candidates(limit)
        if self._looks_like_pinyin(self.buffer):
            self._pinyin_mode.buffer = self.buffer
            pinyin_cands = self._pinyin_mode.candidates(limit)
        # Wubi first if buffer ends in a wubi-shaped code; otherwise pinyin first.
        merged = wubi_cands + pinyin_cands
        # Deduplicate by text, keep first occurrence.
        seen: set[str] = set()
        unique: list[Candidate] = []
        for c in merged:
            if c.text in seen:
                continue
            seen.add(c.text)
            unique.append(c)
        return unique[self._page_offset : self._page_offset + limit]

    def select(self, index: int) -> KeyResult:
        # Grab all merged candidates and apply _page_offset so second-page
        # selections land on the right entry.
        all_cands = self.candidates(limit=9999)
        pos = self._page_offset + index
        if 0 <= pos < len(all_cands):
            return KeyResult(handled=True, commit=all_cands[pos].text, clear=True)
        return KeyResult(handled=False)

    def page(self, direction: int) -> KeyResult:
        self._page_offset = max(0, self._page_offset + direction * 9)
        return KeyResult(handled=True)

    def commit(self) -> Optional[str]:
        if not self.buffer:
            return None
        cands = self.candidates(limit=1)
        if cands:
            return cands[0].text
        # Last resort: commit the raw buffer so the user doesn't lose input.
        return self.buffer

    # ---- Heuristics ----

    def _looks_like_wubi(self, buf: str) -> bool:
        if not buf:
            return True
        if len(buf) > 4:
            return False
        if any(c.isdigit() for c in buf):
            return False
        # Conservative: only treat as wubi when the buffer is an actual
        # wubi prefix in the trie.  The first-key hint is a last-resort
        # fallback when the trie is not yet attached (attach_wubi runs
        # after construction in the engine).
        if self._wubi_mode is not None:
            return self._wubi_mode._trie.has_prefix(buf)
        return buf[0] in _WUBI_FIRST_KEY_HINTS

    def _looks_like_pinyin(self, buf: str) -> bool:
        if not buf:
            return True
        if len(buf) > 6:
            return False
        if buf[-1] in "12345":
            return True
        # Pinyin can be 1-6 letters; the same letters are wubi, so we always
        # try pinyin too.  This is the safe default.
        return True
