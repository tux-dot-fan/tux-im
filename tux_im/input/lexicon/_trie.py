"""Pure data structures: Trie, LexEntry, _TrieNode.

No file I/O, no logging, no side-effects.  Fully deterministic and
unit-testable in complete isolation from the rest of the IME.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
class LexEntry:
    """A single (word, code, freq) entry at a trie terminal node."""

    word: str
    freq: int = 0
    code: str = ""  # pinyin or wubi code


@dataclass
class _TrieNode:
    children: dict[str, _TrieNode] = field(default_factory=dict)
    entries: list[LexEntry] = field(default_factory=list)
    is_word: bool = False


class Trie:
    """Generic prefix trie for IME lookup.

    Keys are lowercased strings (a-z + digits 1-5 for pinyin, a-z for wubi).
    Each terminal node holds a list of ``LexEntry`` sorted by frequency desc.
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

    def has_entry(self, code: str, word: str) -> bool:
        """Check if a specific (code, word) entry exists in the trie."""
        code = code.lower().strip()
        node = self._root
        for ch in code:
            if ch not in node.children:
                return False
            node = node.children[ch]
        if not node.is_word:
            return False
        return any(e.word == word for e in node.entries)

    def lookup_prefix(self, prefix: str) -> list[LexEntry]:
        """Return all entries whose code starts with ``prefix``.

        Unlike ``lookup`` which requires an exact code match, this
        collects entries from every terminal node in the subtree rooted
        at the prefix node.  Used by PinyinMode so the user sees
        candidates while still typing a partial syllable (e.g. "ni"
        matches "ni3", "ni4", …).
        """
        prefix = prefix.lower().strip()
        node = self._root
        for ch in prefix:
            if ch not in node.children:
                return []
            node = node.children[ch]
        result: list[LexEntry] = []
        stack = [node]
        while stack:
            n = stack.pop()
            if n.is_word:
                result.extend(n.entries)
            for child in n.children.values():
                stack.append(child)
        return result

    def iter_words(self) -> Iterator[LexEntry]:
        stack = [(self._root, "")]
        while stack:
            node, prefix = stack.pop()
            if node.is_word:
                yield from node.entries
            for ch, child in node.children.items():
                stack.append((child, prefix + ch))
