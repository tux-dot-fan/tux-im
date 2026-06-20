"""Lexicon loading and prefix-trie data structures."""

from __future__ import annotations

import atexit
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional

log = logging.getLogger(__name__)


@dataclass
class LexEntry:
    word: str
    freq: int = 0
    code: str = ""  # pinyin or wubi code


@dataclass
class _TrieNode:
    children: dict[str, "_TrieNode"] = field(default_factory=dict)
    entries: list[LexEntry] = field(default_factory=list)
    is_word: bool = False


class Trie:
    """Generic prefix trie for IME lookup.

    Keys are lowercased strings (a-z + digits 1-5 for pinyin, a-z for wubi).
    Each terminal node holds a list of `LexEntry` sorted by frequency desc.
    """

    __slots__ = ("_root", "_size")

    def __init__(self) -> None:
        self._root = _TrieNode()
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def insert(self, code: str, word: str, freq: int = 0) -> None:
        code = code.lower().strip()
        if not code or not word:
            return
        node = self._root
        for ch in code:
            node = node.children.setdefault(ch, _TrieNode())
        if not node.is_word:
            self._size += 1
        node.entries.append(LexEntry(word=word, freq=freq, code=code))
        node.is_word = True
        # Keep entries sorted by frequency desc; insertion order as tiebreaker.
        node.entries.sort(key=lambda e: (-e.freq, e.word))

    def boost(self, code: str, word: str, delta: int = 10) -> None:
        """Increase the frequency of an existing (code, word) entry by delta.
        If the entry does not exist this is a no-op."""
        code = code.lower().strip()
        node = self._root
        for ch in code:
            if ch not in node.children:
                return
            node = node.children[ch]
        if not node.is_word:
            return
        for e in node.entries:
            if e.word == word:
                e.freq += delta
                break
        node.entries.sort(key=lambda e: (-e.freq, e.word))

    def has_prefix(self, prefix: str) -> bool:
        prefix = prefix.lower()
        node = self._root
        for ch in prefix:
            if ch not in node.children:
                return False
            node = node.children[ch]
        return True

    def lookup(self, code: str) -> list[LexEntry]:
        code = code.lower()
        node = self._root
        for ch in code:
            if ch not in node.children:
                return []
            node = node.children[ch]
        return list(node.entries)

    def exact(self, code: str) -> bool:
        code = code.lower()
        node = self._root
        for ch in code:
            if ch not in node.children:
                return False
            node = node.children[ch]
        return node.is_word

    def iter_words(self) -> Iterator[LexEntry]:
        stack = [(self._root, "")]
        while stack:
            node, prefix = stack.pop()
            if node.is_word:
                yield from node.entries
            for ch, child in node.children.items():
                stack.append((child, prefix + ch))


# ---------- File loaders ----------

_RIME_LINE = re.compile(r"^(\S+)\s+(\S+)(?:\s+(\d+))?\s*$")


def load_rime_dict(path: Path) -> Iterator[tuple[str, str, int]]:
    """Parse a RIME-format dict file. Yields (word, code, freq)."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("---"):
                continue
            m = _RIME_LINE.match(line)
            if not m:
                continue
            word, code, freq = m.group(1), m.group(2), m.group(3) or "0"
            yield word, code, int(freq)


# ---------- Lexicon (collection of tries) ----------


@dataclass
class Lexicon:
    pinyin: Trie = field(default_factory=Trie)
    wubi: Trie = field(default_factory=Trie)

    # Paths set by load(); used by _schedule_flush().
    _user_words_path: Path = field(default=None, repr=False)  # type: ignore[assignment]
    _dirty: bool = field(default=False, repr=False)
    _flush_timer: Callable | None = field(default=None, repr=False)

    @classmethod
    def load(cls, config) -> "Lexicon":  # noqa: ANN001
        lex = cls()
        # Load system dictionaries first.
        for path, scheme in _discover_dicts(config.dict.search_paths):
            trie = lex.pinyin if scheme == "pinyin" else lex.wubi
            count = 0
            for word, code, freq in load_rime_dict(path):
                trie.insert(code, word, freq)
                count += 1
            log.info("Loaded %d entries from %s into %s trie", count, path, scheme)
        # Overlay user-learned words on top.
        user_path = Path(config.dict.user_words_path)
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
    def _write_user_words(fh, trie: Trie) -> None:
        """Write every entry in `trie` as a TSV line."""
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


def _iter_user_words(path: Path) -> Iterator[tuple[str, str, int]]:
    """Parse a user-word TSV file. Yields (word, code, freq)."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                log.warning("_iter_user_words: line %d in %s has %d fields, "
                            "expected 3, skipping: %r", lineno, path, len(parts), line)
                continue
            word, code, freq_s = parts
            try:
                freq = int(freq_s)
            except ValueError:
                log.warning("_iter_user_words: line %d: freq %r is not an int, skipping",
                           lineno, freq_s)
                continue
            yield word, code, freq


def _discover_dicts(
    paths: Iterable[str],
) -> Iterator[tuple[Path, str]]:
    """Expand a list of (path, scheme) entries into (file, scheme) tuples.

    Scheme is detected from the filename:
      - contains "pinyin" or "luna" or "terra"  -> pinyin
      - contains "wubi"                         -> wubi
      - contains "cangjie" or "stroke" or "bopomofo" -> skipped (unsupported)
    """
    seen: set[Path] = set()
    for raw in paths:
        p = Path(raw).expanduser()
        if not p.exists():
            continue
        candidates: list[Path]
        if p.is_file():
            candidates = [p]
        else:
            candidates = sorted(p.glob("*.dict.yaml"))
        for f in candidates:
            if f in seen:
                continue
            seen.add(f)
            name = f.name.lower()
            if "pinyin" in name or "luna" in name or "terra" in name:
                yield f, "pinyin"
            elif "wubi" in name:
                yield f, "wubi"
            # else: skip (cangjie, stroke, bopomofo, etc.)
