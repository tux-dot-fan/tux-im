"""File I/O for lexicon loading and user-word persistence.

Handles:
- Rime dict file format parsing (load_rime_dict)
- User-word TSV parsing (_iter_user_words)
- System dict discovery (_discover_dicts)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable, Iterator

log = logging.getLogger(__name__)

# Rime dict files come in two flavours:
#   3-column:  word<TAB>code<TAB>freq            (e.g. pinyin tables, user words)
#   4-column:  word<TAB>code<TAB>freq<TAB>stem   (e.g. wubi86, used for
#             affix/derivative generation — we ignore the stem column but
#             must still match the line)
# We try the 4-column pattern first; if it fails, fall back to the
# 3-column pattern.  This used to be a single (\S+)-based regex which,
# due to greedy \S+, swallowed the entire line on 4-column input and
# silently dropped every entry (notably all 25 single-letter wubi
# "level-1" codes like "工" -> "a").
_RIME_LINE_4COL = re.compile(r"^(\S+)\s+(\S+)\s+(\d+)(?:\s+\S+)?\s*$")
_RIME_LINE_3COL = re.compile(r"^(\S+)\s+(\S+)(?:\s+(\d+))?\s*$")


def load_rime_dict(path: Path) -> Iterator[tuple[str, str, int]]:
    """Parse a RIME-format dict file. Yields (word, code, freq).

    Handles both 3-column (``word<TAB>code<TAB>freq``) and 4-column
    (``word<TAB>code<TAB>freq<TAB>stem``) lines; the ``stem`` column is
    ignored (we only use the first three).  Comments (``#`` at start of
    line) and Rime YAML headers (``---``) are skipped.
    """
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("---"):
                continue
            m = _RIME_LINE_4COL.match(line)
            if m:
                word, code, freq = m.group(1), m.group(2), m.group(3)
            else:
                m = _RIME_LINE_3COL.match(line)
                if not m:
                    continue
                word, code, freq = m.group(1), m.group(2), m.group(3) or "0"
            yield word, code, int(freq)


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
