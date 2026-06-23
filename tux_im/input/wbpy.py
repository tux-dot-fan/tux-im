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

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus

from tux_im.input.base import Candidate, InputMode, KeyResult
from tux_im.input.lexicon import Trie
from tux_im.input.wubi import WubiMode

log = logging.getLogger(__name__)

# Letters that are *very* common as Wubi first keys.  Used to bias
# the heuristic: if the buffer ends in a wubi code and starts with one
# of these, treat as Wubi.
_WUBI_FIRST_KEY_HINTS = set("ghklmnotvy")


class WbpyMode:
    """Mixed Wubi + Google Pinyin input mode (86 wubi + google pinyin).

    In wbpy mode every key is fed to BOTH engines in parallel — we do NOT
    pick one.  This is the whole point of wbpy: the user might be mid-way
    through typing a wubi code that happens to also be valid pinyin
    (e.g. "gg" — wubi 码位 + "gg" 拼音无意义，但前几个字母常有歧义)
    and we want the lookup table to show BOTH candidate lists at once.

    The two engines have very different buffer semantics:
      - Wubi is 1-4 ASCII letters.  Tone digits (1-5) are NOT valid wubi
        codes — the wubi engine rejects them.
      - Google Pinyin is 1-6 letters, optionally followed by a single
        tone digit.  Tone digits ARE part of the pinyin buffer.

    To avoid the two buffers fighting each other, we maintain the
    ``self.buffer`` (what the user sees) but the engines have their own
    internal buffers that we never overwrite from outside.  After each
    key we update ``self.buffer`` to the *union* of what was added:
      - If the key was a letter: append to both engines' buffers.
      - If the key was a tone digit (1-5): append to the pinyin buffer
        only; do NOT touch the wubi buffer.
      - The visible buffer is the pinyin buffer (which includes the
        tone digit) so the user can see their input reflected.
    """

    name = "wbpy"
    buffer: str
    cursor: int

    def __init__(self, pinyin_trie: Trie, config: object) -> None:
        # The pinyin half is ALWAYS the Google Pinyin full-sentence decoder.
        from tux_im.input.google_pinyin_mode import GooglePinyinMode
        self._pinyin_mode: InputMode = GooglePinyinMode(pinyin_trie, config)
        # Wubi half is injected by the engine via attach_wubi() because the
        # engine has both tries available at construction time.
        self._wubi_mode: WubiMode | None = None
        self._config = config
        # The visible buffer (what the user sees in the preedit area) is
        # the pinyin engine's buffer — it includes tone digits and is the
        # source of truth for "what the user typed".
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

    def feed_key(self, keyval: int, state: int) -> KeyResult | None:
        key = IBus.keyval_name(keyval)
        if key is None:
            return None
        ch = key.lower()
        if len(ch) != 1 or (not ch.isalpha() and ch not in "12345"):
            return None

        is_tone = ch in "12345"
        wubi_handled = False
        pinyin_handled = False
        # The pinyin engine is the source of truth for the visible
        # buffer (it accepts letters AND tone digits, returns a
        # full-sentence candidate).  We let it own its own buffer
        # via its own feed_key.  The wubi engine's buffer is a
        # derived view that is RESET every time a tone digit
        # appears in the input: wubi codes never contain digits, so
        # a tone digit marks the end of the previous wubi attempt
        # and the start of a new one (or just a pinyin segment).
        # This way "ni3kld" → wubi buffer is "kld", not "nikld".
        #
        # Length cap: 19 consecutive "c" crashes libgooglepinyin's
        # internal MatrixSearch with assertion failure.  The
        # library's own im_set_max_lens caps at 30 but a single
        # all-consonant buffer of ~19 letters still trips an
        # internal assert in dict match.  Cap the pinyin engine's
        # buffer at 16 (a reasonable pinyin sentence length: ~6
        # letters per syllable × 2-3 syllables).
        _MAX_PINYIN_LEN = 16
        if (
            self._pinyin_mode is not None
            and len(self._pinyin_mode.buffer) >= _MAX_PINYIN_LEN
            and not is_tone
        ):
            # Reject the letter — don't pass it to the pinyin
            # engine.  Still update the wubi half so the candidate
            # panel doesn't go stale.
            if self._wubi_mode is not None:
                if is_tone:
                    self._wubi_mode.buffer = ""
                else:
                    self._wubi_mode.buffer += ch
                wubi_handled = True
            self.buffer = self._pinyin_mode.buffer
            self.cursor = len(self.buffer)
            return KeyResult(handled=wubi_handled)
        if self._pinyin_mode is not None:
            res = self._pinyin_mode.feed_key(keyval, state)
            pinyin_handled = bool(res and res.handled)
        if self._wubi_mode is not None:
            if is_tone:
                # Tone digit: wubi segment boundary.  Reset wubi
                # buffer to empty so the next letter starts a new
                # wubi code.
                self._wubi_mode.buffer = ""
            else:
                # Letter: append to the wubi buffer.  We assign
                # directly rather than calling wubi.feed_key so
                # the 4-char cap and prefix-validity checks do not
                # cause the two halves to drift out of sync.
                self._wubi_mode.buffer += ch
            wubi_handled = True
        # The visible buffer mirrors the pinyin engine's buffer.
        self.buffer = self._pinyin_mode.buffer
        self.cursor = len(self.buffer)
        if wubi_handled or pinyin_handled:
            return KeyResult(handled=True)
        return None

    def candidates(self, limit: int = 9) -> list[Candidate]:
        if not self.buffer:
            return []
        # In wbpy mode we always query BOTH engines.  The wubi engine's
        # own buffer tracks only letters (tone digits are not fed to it),
        # so it stays valid even when the visible buffer contains tones.
        wubi_cands: list[Candidate] = []
        if self._wubi_mode is not None and self._wubi_mode.buffer:
            wubi_cands = self._wubi_mode.candidates(limit)
        pinyin_cands = self._pinyin_mode.candidates(limit)
        # Wubi candidates first, then pinyin candidates, dedup by text.
        merged = wubi_cands + pinyin_cands
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

    def backspace(self) -> bool:
        """Delete one character from the user's input.

        In wbpy mode the pinyin sub-engine owns the visible buffer
        and the google pinyin decoder state.  The wubi sub-engine's
        buffer is a derived view: every letter after the last tone
        digit (or all letters if there is no tone digit yet).
        We delegate the backspace to the pinyin engine — it
        correctly rolls back its own buffer AND resets/re-feeds
        the decoder — and then re-derive the wubi buffer from the
        new visible state.
        """
        if not self.buffer:
            return False
        # Let the pinyin engine handle the actual buffer + decoder
        # rollback.  It returns False when the buffer is already
        # empty (defensive — should not happen since we just
        # checked).
        if self._pinyin_mode is not None and not self._pinyin_mode.backspace():
            return False
        # Update visible cursor/buffer from pinyin engine.
        self.buffer = self._pinyin_mode.buffer
        self.cursor = len(self.buffer)
        # Re-derive the wubi engine's buffer: the segment of the
        # visible buffer that follows the LAST tone digit (or the
        # whole buffer if no tone digit has been typed).  This
        # matches the rule used in feed_key so the two stay in
        # sync after backspace.
        if self._wubi_mode is not None:
            buf = self.buffer
            last_tone_idx = max(
                (i for i, c in enumerate(buf) if c in "12345"),
                default=-1,
            )
            self._wubi_mode.buffer = buf[last_tone_idx + 1:]
        return True

    def full_sentence(self) -> str | None:
        """Return the text that will be committed on space: the top entry
        from the merged (deduplicated) candidate list, i.e. the first
        wubi candidate if any, otherwise the first pinyin candidate,
        falling back to the raw buffer."""
        if not self.buffer:
            return None
        # Grab a large enough window so we don't miss duplicates at the front.
        all_cands = self.candidates(limit=9999)
        if all_cands:
            return all_cands[0].text
        return self.buffer

    def commit(self) -> str | None:
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
