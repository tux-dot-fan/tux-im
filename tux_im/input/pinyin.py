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

# ASCII punctuation that auto-commits the current buffer AND converts to Chinese.
# E.g. typing "wo" then "." commits "我。" in one shot.
_ASCII_TO_CHINESE = {
    ".": "\u3002",   # . -> 。
    ",": "\uff0c",   # , -> ，
    ";": "\uff1b",   # ; -> ；
    ":": "\uff1a",   # : -> ：
    "?": "\uff1f",   # ? -> ？
    "!": "\uff01",   # ! -> ！
    "<": "\u300a",   # < -> 《
    ">": "\u300b",   # > -> 》
    "(": "\uff08",   # ( -> （
    ")": "\uff09",   # ) -> ）
    "[": "\u3010",   # [ -> 【
    "]": "\u3011",   # ] -> 】
    "-": "\u2014",   # - -> — (em dash)
    "'": "\u2019",   # ' -> ' (right single quote)
    "\"": "\u201d",  # " -> " (right double quote)
}


class PinyinMode:
    """Buffers pinyin (with tone numbers) and looks up candidates in `PinyinTrie`.

    Supports "连打" (consecutive typing): the user types the full pinyin of a
    multi-syllable word at once (e.g. ``nihao`` for "你好") and we segment
    the buffer into syllables automatically on commit and selection.
    """

    name = "pinyin"
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

        # Punctuation: commit current buffer and convert to Chinese equivalent.
        # Empty buffer -> pass through so the app gets the raw ASCII.
        if len(ch) == 1 and ch in _ASCII_TO_CHINESE:
            if not self.buffer:
                return None
            committed = self.commit() or ""
            chinese = _ASCII_TO_CHINESE[ch]
            log.debug("PinyinMode.feed_key: punct %r -> commit=%r + punct=%r",
                      ch, committed, chinese)
            self.reset()
            return KeyResult(handled=True, commit=committed + chinese)

        return None

    # ---- 连打 (consecutive typing) support ----

    # Valid single-character pinyin initials (v=u for ü) and finals.
    # If has_prefix fails we fall back to these so single-letter input
    # like "a" or "i" is still treated as a valid partial pinyin syllable.
    _SINGLE_LETTER_PINYIN = {"a", "o", "e", "i", "u", "v"}

    def segment(self, code: str) -> list[str]:
        """Split a buffer like 'nihao' or 'ni3hao' into pinyin syllables.

        Returns a list of segment codes (with their trailing tone digit
        preserved). Uses greedy forward matching: at each position try the
        longest prefix that is a valid pinyin code in the trie. The last
        segment may be a partial code (still being typed) -- callers
        should check ``has_prefix`` if they need to distinguish.
        """
        if not code:
            return []
        # Strip a trailing tone digit and reattach it to the last segment.
        tone = ""
        body = code
        if body and body[-1].isdigit():
            tone = body[-1]
            body = body[:-1]

        segments: list[str] = []
        i = 0
        n = len(body)
        while i < n:
            # Try the longest prefix first, then shrink until we find a
            # valid code in the trie. Bail out when nothing matches.
            found = False
            for j in range(n, i, -1):
                piece = body[i:j]
                if self._trie.has_prefix(piece):
                    segments.append(piece + (tone if j == n else ""))
                    i = j
                    found = True
                    break
            if not found:
                # No valid pinyin starts at position i. If it's a single
                # letter that looks like a pinyin vowel/initial, treat it
                # as a valid partial syllable so the user can type one
                # letter at a time. Otherwise treat the letter as an
                # invalid segment (user made a typo).
                ch = body[i]
                if ch.lower() in self._SINGLE_LETTER_PINYIN:
                    segments.append(ch + (tone if i + 1 == n else ""))
                    i += 1
                else:
                    # Skip one character and keep trying; this prevents
                    # the loop from spinning forever on bad input.
                    segments.append(ch)
                    i += 1
        if not segments:
            return []
        if tone and segments[-1][-1] != tone:
            segments[-1] = segments[-1] + tone
        return segments

    def commit(self) -> Optional[str]:
        if not self.buffer:
            return None
        # 连打: split the buffer into syllables and concatenate the first
        # candidate of each. 'nihao' -> ['ni', 'hao'] -> '你好'.
        segments = self.segment(self.buffer)
        parts: list[str] = []
        for seg in segments:
            # Trie keys include the tone digit (ni3, hao3).  Pass the full
            # syllable so the correct entry is found.
            entries = self._trie.lookup(seg)
            if entries:
                parts.append(entries[0].word)
            else:
                # Unknown syllable -- fall back to raw so the user keeps it.
                parts.append(seg)
        return "".join(parts)

    def candidates(self, limit: int = 9) -> list[Candidate]:
        """Show candidates for the *first* (incomplete) segment.

        连打 mode: the user is mid-typing a multi-syllable word. The first
        segment is still being entered; remaining segments are committed
        silently with their top candidate. Returns up to ``limit``
        candidates for the first segment.
        """
        if not self.buffer:
            return []
        segments = self.segment(self.buffer)
        if not segments:
            return []
        first = segments[0]
        # Trie keys include the tone digit (ni3, hao3).  Pass the full
        # syllable to lookup so the correct entry is found.
        entries = self._trie.lookup(first)
        cands = [_entry_to_candidate(e) for e in entries]
        return cands[self._page_offset : self._page_offset + limit]

    def select(self, index: int) -> KeyResult:
        """Select candidate for first segment, commit rest, return full text."""
        if not self.buffer:
            return KeyResult(handled=False)
        segments = self.segment(self.buffer)
        if not segments:
            return KeyResult(handled=False)
        first = segments[0]
        # Trie keys include the tone digit (ni3, hao3).  Pass the full
        # syllable so the correct entry is found.
        entries = self._trie.lookup(first)
        if not (0 <= index < len(entries)):
            return KeyResult(handled=False)
        parts = [entries[index].word]
        for seg in segments[1:]:
            tail = self._trie.lookup(seg)
            parts.append(tail[0].word if tail else seg)
        return KeyResult(handled=True, commit="".join(parts), clear=True)

    def page(self, direction: int) -> KeyResult:
        self._page_offset = max(0, self._page_offset + direction * 9)
        return KeyResult(handled=True)

    def full_sentence(self) -> str | None:
        """No sentence-level decoding; return None."""
        return None


def _entry_to_candidate(e: LexEntry) -> Candidate:
    return Candidate(text=e.word, display=e.word, comment=e.code, freq=e.freq)
