"""Google Pinyin full-sentence input mode.

libgooglepinyin (Apache 2.0): https://github.com/qgears/libgooglepinyin
Dictionary: dict_pinyin.dat (1.1 MB, 65k+ entries, pre-built from rawdict)

Architecture
============
libgooglepinyin has two key APIs:
  - im_search(pinyin_str) → full-sentence candidates; ALWAYS resets locked state
  - im_choose(cand_id)     → locks first word of candidate cand_id;
      decoder re-decodes remaining pinyin; returns new candidate count

Key behavioral facts (verified empirically in C++):
  1. im_search() ALWAYS resets fixed_len to 0.
     After im_choose(i), calling im_search(full_string) gives fixed_len=0.
  2. After im_choose(i), the new candidate list at index 0 is the FULL
     remaining decoded sentence; indices 1+ are individual words of the remaining.
  3. The REMAINING pinyin is NOT automatically trimmed by im_choose();
     we must call im_search(remaining_pinyin) ourselves to get candidates
     for the remaining portion (without resetting the locked state).

Per-word-lock workflow (the correct algorithm):
  1. search(full_string) → candidates for all pinyin
  2. choose(i) → locks first word; decoder re-decodes remaining pinyin internally
     - new_word = cand_text(i) after choose (this is the FULL decoded remaining)
     - cumulative_fixed += len(new_word)
     - call search(remaining_pinyin) → candidates for the suffix
     - remaining_pinyin = remaining_pinyin[ spl_start[len(new_word)] ]
  3. Repeat step 2.

After choose(i):
  - cand_text(0) = FULL remaining decoded string
  - cand_text(i) = the ith word/phrase of the remaining (i >= 1)
  - The USER chose cand_text(adj) where adj = user's selected index
  - new_word = cand_text(adj) = the newly locked portion
  - cumulative_fixed += len(new_word)  ← KEY: we track this ourselves
  - Trim remaining pinyin using spl_start[len(new_word)]
  - search(remaining_pinyin) for next candidates
"""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from tux_im.input.base import Candidate, InputMode, KeyResult

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

# ── libgooglepinyin singleton ──────────────────────────────────────────────────

_lib = None


def _load_lib():
    global _lib
    if _lib is not None:
        return _lib

    for path in (
        "/usr/lib/x86_64-linux-gnu/libgooglepinyin.so",
        "/usr/local/lib/libgooglepinyin.so",
        "libgooglepinyin.so",
    ):
        if os.path.exists(path):
            _lib = ctypes.CDLL(path)
            break
    else:
        for p in (
            "/usr/lib/x86_64-linux-gnu/libgooglepinyin.so",
            "/usr/local/lib/libgooglepinyin.so",
            "libgooglepinyin.so",
        ):
            print(f"DEBUG: path={p!r} exists={os.path.exists(p)}", flush=True)
        raise FileNotFoundError(
            "libgooglepinyin.so not found. "
            "Install: sudo apt install libgooglepinyin0-dev"
        )

    def _sig(restype: type, *argtypes) -> callable:
        def decorator(func: callable) -> callable:
            func.restype = restype
            func.argtypes = list(argtypes)
            return func

        return decorator

    _sig(ctypes.c_bool, ctypes.c_char_p, ctypes.c_char_p)(_lib.im_open_decoder)
    _sig(None)(_lib.im_close_decoder)
    _sig(ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t)(_lib.im_search)
    _sig(ctypes.c_size_t, ctypes.c_size_t)(_lib.im_choose)
    _sig(ctypes.c_size_t)(_lib.im_cancel_last_choice)
    _sig(None)(_lib.im_reset_search)
    _sig(ctypes.c_size_t)(_lib.im_get_fixed_len)
    _sig(ctypes.c_bool)(_lib.im_cancel_input)
    _sig(None, ctypes.c_size_t, ctypes.c_size_t)(_lib.im_set_max_lens)

    _lib.im_get_sps_str.restype = ctypes.c_char_p
    _lib.im_get_sps_str.argtypes = [ctypes.POINTER(ctypes.c_size_t)]

    char16 = ctypes.c_uint16
    _lib.im_get_candidate.restype = ctypes.POINTER(char16)
    _lib.im_get_candidate.argtypes = [
        ctypes.c_size_t,
        ctypes.POINTER(char16),
        ctypes.c_size_t,
    ]

    _lib.im_get_spl_start_pos.restype = ctypes.c_size_t
    _lib.im_get_spl_start_pos.argtypes = [
        ctypes.POINTER(ctypes.POINTER(ctypes.c_uint16))
    ]

    _sig(None)(_lib.im_flush_cache)

    return _lib


class _Decoder:
    """ctypes wrapper for libgooglepinyin decoder — opened once, shared."""

    __slots__ = ("_lib", "_open")

    def __init__(self, sys_dict: str, user_dict: str) -> None:
        lib = _load_lib()
        ok = lib.im_open_decoder(sys_dict.encode(), user_dict.encode())
        if not ok:
            raise RuntimeError(f"im_open_decoder failed for {sys_dict!r}")
        lib.im_set_max_lens(30, 50)
        self._lib = lib
        self._open = True

    def close(self) -> None:
        if self._open:
            self._lib.im_flush_cache()
            self._lib.im_close_decoder()
            self._open = False

    def search(self, pinyin: str) -> int:
        """Decode pinyin string. Returns candidate count. Resets locked state."""
        b = pinyin.encode("ascii")
        self._lib.im_reset_search()
        return self._lib.im_search(b, len(b))

    def choose(self, cand_id: int) -> int:
        """Lock first word of candidate cand_id. Returns NEW candidate count for
        the remaining (unfixed) pinyin. Does NOT reset locked state."""
        return self._lib.im_choose(cand_id)

    def cancel_last(self) -> int:
        return self._lib.im_cancel_last_choice()

    def reset(self) -> None:
        self._lib.im_reset_search()
        self._lib.im_cancel_input()

    def fixed_len(self) -> int:
        """Number of Chinese chars locked so far (cumulative across choose calls)."""
        return self._lib.im_get_fixed_len()

    def _spl_start(self):
        """Return spelling-segment byte boundaries as list[int]."""
        ptr = ctypes.POINTER(ctypes.c_uint16)()
        n = self._lib.im_get_spl_start_pos(ptr)
        return [ptr[i] for i in range(n + 1)] if n > 0 else [0]

    def _cand_text(self, i: int) -> str:
        """Return candidate text (Chinese string) at index i."""
        buf = (ctypes.c_uint16 * 256)(*([0] * 256))
        ret = self._lib.im_get_candidate(
            i, ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint16)), 255
        )
        if not ret:
            return ""
        chars = []
        for c in buf:
            if c == 0:
                break
            if c < 0xD800:
                chars.append(chr(c))
            elif c < 0xE000:
                continue
            else:
                chars.append(chr(c))
        return "".join(chars)


# ── Global shared decoder ─────────────────────────────────────────────────────

_decoder: _Decoder | None = None
_DICT_SYS = "/usr/lib/x86_64-linux-gnu/googlepinyin/data/dict_pinyin.dat"


def _get_decoder() -> _Decoder:
    global _decoder
    if _decoder is None:
        user_dict = str(Path.home() / ".local/share/tux-im/google_pinyin_user.dat")
        Path(user_dict).parent.mkdir(parents=True, exist_ok=True)
        _decoder = _Decoder(_DICT_SYS, user_dict)
    return _decoder


# ── ASCII punctuation → Chinese ───────────────────────────────────────────────

_ASCII_TO_CHINESE = {
    "period": "\u3002",
    "comma": "\uff0c",
    "semicolon": "\uff1b",
    "colon": "\uff1a",
    "question": "\uff1f",
    "exclam": "\uff01",
    "less": "\u300a",
    "greater": "\u300b",
    "parenleft": "\uff08",
    "parenright": "\uff09",
    "bracketleft": "\u3010",
    "bracketright": "\u3011",
    "minus": "\u2014",
    "apostrophe": "\u2019",
    "quotedbl": "\u201d",
}


# ── GooglePinyinMode ──────────────────────────────────────────────────────────


class GooglePinyinMode:
    """Full-sentence pinyin input using libgooglepinyin.

    Implements the ``InputMode`` protocol.  Users type a full pinyin string
    (e.g. ``wozhidaozhidaonihao``) and see sentence candidates.  Selecting a
    candidate locks its first word; the engine re-decodes the remaining pinyin,
    exactly like Google Pinyin / Sogou Pinyin.

    ``name`` is ``"pinyin"`` so this mode REPLACES the old Trie-based
    PinyinMode without any engine or config changes.
    """

    name = "google"
    buffer: str
    cursor: int

    def __init__(self, _trie: object, _config: object) -> None:
        # _trie and _config: accepted for InputMode protocol compatibility,
        # but all decoding is handled internally by libgooglepinyin.
        self._dec = _get_decoder()
        self._dec.reset()

        # ── Protocol-required state ─────────────────────────────────────────
        self.buffer = ""
        self.cursor = 0

        # ── Internal state ─────────────────────────────────────────────────
        # Cumulative Chinese chars locked by choose() calls (tracked in Python,
        # not from dec.fixed_len() which resets after search())
        self._cumulative_fixed: int = 0

        # Pinyin bytes still to be decoded (remaining after locked prefix)
        self._remaining_pinyin: str = ""

        # Chinese text that has been locked (accumulated across choose calls)
        self._fixed_text: str = ""

        # Total candidate count from the last search/choose call
        self._total_cands: int = 0

        # Page offset for candidate pagination
        self._page_offset: int = 0

    def reset(self) -> None:
        self._dec.reset()
        self.buffer = ""
        self._cumulative_fixed = 0
        self._remaining_pinyin = ""
        self._fixed_text = ""
        self._total_cands = 0
        self._page_offset = 0
        self.cursor = 0

    # ── Internal helpers ────────────────────────────────────────────────────

    def _trim_pinyin_for_remaining(self, new_word: str) -> None:
        """Trim pinyin bytes for the newly locked word `new_word`.

        The decoder's spelling-segment boundaries (spl_start) give us the byte
        range for each pinyin syllable.  By computing how many Chinese chars
        `new_word` has, we can find how many syllables that is and trim the
        corresponding bytes from the remaining pinyin.
        """
        if not new_word or not self._remaining_pinyin:
            return
        spl = self._dec._spl_start()
        n_splits = len(spl) - 1
        if n_splits == 0:
            self._remaining_pinyin = ""
            return
        # How many syllables did `new_word` consume?
        # new_word_len (in Chinese chars) ≈ new_word byte count (UTF-8 Chinese ≈ 3 bytes,
        # but for simplicity we use the cumulative approach: each Chinese char
        # from new_word corresponds to one additional syllable in spl).
        # CORRECTION: new_word IS the text for some syllables; use len(new_word)
        # as the number of Chinese chars/syllables consumed.
        n_chars = len(new_word)
        if n_chars >= n_splits:
            self._remaining_pinyin = ""
        else:
            trim_bytes = spl[n_chars]
            self._remaining_pinyin = self._remaining_pinyin[trim_bytes:]

    def _build_candidates(self, limit: int = 9) -> list[Candidate]:
        """Build Candidate list: index 0 = full sentence (top-ranked), then word-level options."""
        results: list[Candidate] = []
        for i in range(0, self._total_cands):
            text = self._dec._cand_text(i)
            if not text:
                break
            # For index 0 (full sentence), prepend locked text;
            # for subsequent entries the decoder already includes it.
            if i == 0:
                full_text = self._fixed_text + text
            else:
                full_text = self._fixed_text + text
            results.append(Candidate(text=full_text, display=full_text))
        offset = self._page_offset
        return results[offset:offset + limit]

    # ── InputMode protocol ─────────────────────────────────────────────────

    def feed_key(self, keyval: int, state: int) -> KeyResult | None:
        from gi.repository import IBus

        key = IBus.keyval_name(keyval)
        if key is None:
            return None
        ch = key.lower()

        # Letter: accumulate in pinyin buffer
        if len(ch) == 1 and ch.isalpha():
            self.buffer += ch
            self.cursor = len(self.buffer)
            # Cap the pinyin string fed to the decoder.  19+ letters of
            # the same consonant crashes libgooglepinyin's
            # MatrixSearch::extend_dmi (assertion failure → SIGABRT →
            # process core dump).  Keep the buffer growing in the
            # visible sense (so the user can still see what they
            # typed) but stop sending it to the decoder past a safe
            # length.  im_set_max_lens caps at 30 already but the
            # crash happens earlier for degenerate inputs.
            _MAX_DECODE_LEN = 16
            if len(self.buffer) <= _MAX_DECODE_LEN:
                self._remaining_pinyin += ch
                self._page_offset = 0
                self._total_cands = self._dec.search(self._remaining_pinyin)
            log.debug(
                "GooglePinyinMode.feed_key: %r, buffer=%r, cands=%d",
                ch, self.buffer, self._total_cands,
            )
            return KeyResult(handled=True)

        # Tone digit: only after letters
        if ch in "12345" and self.buffer:
            self.buffer += ch
            self._remaining_pinyin += ch
            self._page_offset = 0
            self._total_cands = self._dec.search(self._remaining_pinyin)
            self.cursor = len(self.buffer)
            return KeyResult(handled=True)

        # Punctuation: commit current buffer + convert to Chinese equivalent.
        # E.g. typing "nihao" then "." commits "你好" + adds "。" → "你好。"
        if key in _ASCII_TO_CHINESE:
            # Commit current composition if any
            if self._fixed_text or self._remaining_pinyin:
                committed = self.commit() or ""
            else:
                committed = ""
            result = committed + _ASCII_TO_CHINESE[key]
            self.reset()
            return KeyResult(handled=True, commit=result)

        return None

    def candidates(self, limit: int = 9) -> list[Candidate]:
        if not self._remaining_pinyin:
            return []
        return self._build_candidates(limit)

    def full_sentence(self) -> str | None:
        """Return the full decoded sentence (index 0), or None if not available."""
        if not self._remaining_pinyin or self._total_cands == 0:
            return None
        return self._dec._cand_text(0) or None

    def select(self, index: int) -> KeyResult:
        """Lock first word of candidate at adjusted index.

        User sees candidates from im_search(_remaining_pinyin). They pick adj=0
        (full sentence), adj=1 (first word), adj=2 (second word), etc.

        We MUST save the candidate text BEFORE calling choose() because
        choose() mutates the decoder state and cand_text(adj) changes.
        """
        adj = index + self._page_offset
        if adj < 0 or adj >= self._total_cands:
            return KeyResult(handled=False)

        # Save candidate text BEFORE choose (choose() mutates decoder state)
        chosen_text = self._dec._cand_text(adj)
        if not chosen_text:
            return KeyResult(handled=False)

        # Lock first word; get new candidate count for remaining
        self._total_cands = self._dec.choose(adj)

        # The locked text = the word at index adj in the ORIGINAL list
        # new_word may be 1 char ('我'), 2 chars ('我只'), or more (full sentence)
        new_word = chosen_text  # correct: saved before choose() mutated state

        # Update cumulative locked text
        self._fixed_text += new_word
        self._cumulative_fixed += len(new_word)

        # Trim the pinyin that corresponds to the newly locked word
        self._trim_pinyin_for_remaining(new_word)

        # Re-decode remaining pinyin for next candidates
        if self._remaining_pinyin:
            self._total_cands = self._dec.search(self._remaining_pinyin)
            self.buffer = self._remaining_pinyin
            self.cursor = len(self.buffer)
        else:
            self._total_cands = 0
            self.buffer = ""
            self.cursor = 0

        self._page_offset = 0
        log.debug(
            "GooglePinyinMode.select(%d): locked=%r, fixed=%r, "
            "remaining=%r, cands=%d",
            index, new_word, self._fixed_text, self._remaining_pinyin,
            self._total_cands,
        )

        # If no remaining pinyin → commit everything
        if not self._remaining_pinyin:
            result = self._fixed_text
            self.reset()
            return KeyResult(handled=True, commit=result, clear=True)

        return KeyResult(handled=True, clear=True)

    def commit(self) -> str | None:
        """Commit top candidate (called by engine on focus out)."""
        if not self._fixed_text and not self._remaining_pinyin:
            return None

        if self._remaining_pinyin:
            # Save before choose (choose mutates state)
            top = self._dec._cand_text(0) or ""
            self._total_cands = self._dec.choose(0)
            new_word = top
            self._fixed_text += new_word
            self._cumulative_fixed += len(new_word)
            self._trim_pinyin_for_remaining(new_word)

        result = self._fixed_text
        self.reset()
        return result if result else None

    def page(self, direction: int) -> KeyResult:
        self._page_offset = max(0, self._page_offset + direction * 9)
        return KeyResult(handled=True)

    def backspace(self) -> bool:
        # GooglePinyinMode keeps coupled state: visible buffer, the
        # remaining_pinyin fed to the libgooglepinyin decoder, and any
        # locked text from previous choose() calls.  The simplest
        # correct strategy on backspace is to reset the decoder and
        # re-feed the truncated buffer.  Backspace is rare; correctness
        # > incremental efficiency.
        if not self.buffer:
            return False
        new_buf = self.buffer[:-1]
        if self.cursor > 0:
            self.cursor -= 1
        self._dec.reset()
        self._cumulative_fixed = 0
        self._fixed_text = ""
        self._remaining_pinyin = new_buf
        self.buffer = new_buf
        if new_buf:
            self._total_cands = self._dec.search(new_buf)
        else:
            self._total_cands = 0
        self._page_offset = 0
        return True
