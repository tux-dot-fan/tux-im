"""Lexicon: system dict loading and user-word persistence.

Public API
----------
Lexicon     : Main class.  Call ``Lexicon.load(config)`` to build from disk.
Trie        : Prefix trie data structure.  ``trie.insert(code, word, freq)``.
LexEntry    : Dataclass for a single (word, code, freq) entry.
load_rime_dict : Standalone generator for Rime dict files.

Internal structure
------------------
_trie.py        : Pure Trie data structure (no I/O, no side-effects).
_persistence.py : File I/O: TSV read/write, Rime dict parsing, dict discovery.
"""

from __future__ import annotations

import atexit
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, IO, Iterable, Iterator

if TYPE_CHECKING:
    from tux_im.config.config import Config

from tux_im.input.lexicon._persistence import (
    _discover_dicts,
    _iter_user_words,
    load_rime_dict,
)
from tux_im.input.lexicon._trie import LexEntry, Trie

log = logging.getLogger(__name__)


# Re-export public names from submodules for backwards compatibility.
__all__ = ["Lexicon", "Trie", "LexEntry", "load_rime_dict"]


@dataclass
class Lexicon:
    """Collection of pinyin and wubi tries with user-word persistence.

    Built by ``Lexicon.load(config)``.  User-learned words are flushed to
    ``config.dictionary.user_words_path`` on:
      - ``add_user_word()`` call (debounced)
      - ``_flush_now()`` explicit call
      - normal Python exit (via ``atexit``)
      - hot-reload path in ``main.py``

    The file format is TSV: ``word<tab>code<tab>freq`` per line.
    """

    pinyin: Trie = field(default_factory=Trie)
    wubi: Trie = field(default_factory=Trie)

    # Paths set by load(); used by _schedule_flush().
    _user_words_path: Path = field(default=None, repr=False)  # type: ignore[assignment]
    _dirty: bool = field(default=False, repr=False)
    _flush_timer: Callable[[], bool] | None = field(default=None, repr=False)

    @classmethod
    def load(cls, config: Config) -> "Lexicon":  # noqa: ANN001
        lex = cls()
        # Load system dictionaries first.
        for path, scheme in _discover_dicts(config.dictionary.search_paths):
            trie = lex.pinyin if scheme == "pinyin" else lex.wubi
            count = 0
            for word, code, freq in load_rime_dict(path):
                trie.insert(code, word, freq)
                count += 1
            log.info("Loaded %d entries from %s into %s trie", count, path, scheme)
        # Overlay user-learned words on top.
        user_path = Path(config.dictionary.user_words_path)
        lex._user_words_path = user_path
        if user_path.exists():
            n_user = lex._load_user_words(user_path)
            log.info("Merged %d user-word entries from %s", n_user, user_path)
        # Register the flush handler so pending learned words survive a
        # clean shutdown (e.g. ibus-daemon --quit).
        atexit.register(lex._flush_now)
        return lex

    # ---- User-word persistence ----

    def _load_user_words(self, path: Path) -> int:
        """Parse a user-word TSV file and merge entries into the tries.

        Each line: ``word<tab>code<tab>freq``.
        Already-present entries are boosted by the stored freq.
        Unknown entries are inserted with the stored freq.
        Returns the number of entries processed.
        """
        n = 0
        for word, code, freq in _iter_user_words(path):
            trie = self.pinyin if any(c.isdigit() for c in code) else self.wubi
            if trie.exact(code):
                trie.boost(code, word, delta=freq)
            else:
                trie.insert(code, word, freq=freq)
            n += 1
        return n

    def _schedule_flush(self) -> None:
        """Mark lexicon dirty and schedule an async write to disk (debounced).

        Multiple calls before the timer fires only cause one write.
        """
        self._dirty = True
        if self._flush_timer is not None:
            self._flush_timer()
        # else: _flush_now is used (lexicon not yet fully loaded or test mode)

    def _flush_now(self) -> None:
        """Write all dirty user words to the user-words file synchronously.

        This is called from atexit (normal exit) and from the hot-reload
        path.  File is written atomically (write-to-temp + rename) so a
        crash mid-write cannot corrupt the data.
        """
        if not self._dirty or self._user_words_path is None:
            return
        path = self._user_words_path
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tmp.open("w", encoding="utf-8") as fh:
                # Write pinyin entries first, then wubi.
                self._write_user_words(fh, self.pinyin)
                self._write_user_words(fh, self.wubi)
            os.replace(tmp, path)  # atomic on POSIX
            self._dirty = False
            log.debug("User words persisted to %s", path)
        except OSError:
            log.exception("Failed to persist user words to %s", path)
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    @staticmethod
    def _write_user_words(fh: IO[str], trie: "Trie") -> None:
        """Write every entry in ``trie`` as a TSV line."""
        written: set[tuple[str, str]] = set()
        for entry in trie.iter_words():
            key = (entry.word, entry.code)
            if key in written:
                continue
            written.add(key)
            fh.write(f"{entry.word}\t{entry.code}\t{entry.freq}\n")

    def add_user_word(self, code: str, word: str, freq: int = 100) -> None:
        """Add a user-learned word. Detects pinyin vs wubi by code shape."""
        if any(c.isdigit() for c in code):
            self.pinyin.insert(code, word, freq)
        else:
            self.wubi.insert(code, word, freq)
        self._schedule_flush()
