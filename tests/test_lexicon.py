"""Tests for the lexicon / trie data structures."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from tux_im.input.lexicon import (
    Lexicon,
    Trie,
    _iter_user_words,
    load_rime_dict,
)


def test_trie_insert_and_lookup() -> None:
    t = Trie()
    t.insert("ni3", "你", 100)
    t.insert("ni3", "泥", 50)
    t.insert("hao3", "好", 80)
    assert t.exact("ni3")
    assert not t.exact("ni")
    res = t.lookup("ni3")
    assert [e.word for e in res] == ["你", "泥"]
    assert t.has_prefix("n")
    assert t.has_prefix("ni")
    assert not t.has_prefix("z")


def test_trie_size() -> None:
    t = Trie()
    t.insert("a", "甲", 1)
    t.insert("ab", "甲乙", 1)
    t.insert("ab", "甲丙", 1)
    assert len(t) == 2


def test_trie_prefix() -> None:
    t = Trie()
    t.insert("kld", "我", 1)
    t.insert("kldw", "我们", 1)
    assert t.has_prefix("k")
    assert t.has_prefix("kl")
    assert t.has_prefix("kld")
    assert t.has_prefix("kldw")
    assert not t.has_prefix("kldx")


def test_trie_exact() -> None:
    t = Trie()
    t.insert("ni3", "你", 100)
    assert t.exact("ni3") is True
    assert t.exact("ni") is False
    assert t.exact("n") is False


def test_trie_boost() -> None:
    t = Trie()
    t.insert("ni3", "你", 100)
    t.insert("ni3", "泥", 50)
    assert [e.word for e in t.lookup("ni3")] == ["你", "泥"]
    t.boost("ni3", "你", delta=50)
    assert [e.word for e in t.lookup("ni3")] == ["你", "泥"]
    assert t.lookup("ni3")[0].freq == 150
    t.boost("ni3", "泥", delta=100)
    # Both freq=150 now; tiebreaker is word ascending ("你" < "泥").
    assert [e.word for e in t.lookup("ni3")] == ["你", "泥"]
    assert [e.freq for e in t.lookup("ni3")] == [150, 150]


def test_trie_boost_unknown() -> None:
    """Boosting a non-existent entry is a no-op."""
    t = Trie()
    t.insert("ni3", "你", 100)
    t.boost("xyz", "不存在", delta=999)  # should not raise
    assert len(t) == 1  # no new entries


def test_load_rime_dict(tmp_path) -> None:
    p = tmp_path / "test.dict.yaml"
    p.write_text(
        "# header\n"
        "---\n"
        "name: test\n"
        "你\tni3\t100\n"
        "好\thao3\t80\n"
        "我\tkld\t100\n"
    )
    entries = list(load_rime_dict(p))
    assert ("你", "ni3", 100) in entries
    assert ("好", "hao3", 80) in entries
    assert ("我", "kld", 100) in entries


def test_iter_user_words(tmp_path) -> None:
    p = tmp_path / "user_words.txt"
    p.write_text(
        "你好\tni3hao\t50\n"
        "我\two3\t30\n"
        "# comment line\n"
        "他\tha\t20\n"
    )
    entries = list(_iter_user_words(p))
    # Order is file-order (comment lines skipped).
    assert entries == [("你好", "ni3hao", 50), ("我", "wo3", 30), ("他", "ha", 20)]


def test_iter_user_words_bad_lines(tmp_path, caplog) -> None:
    """Malformed lines are skipped with a warning, not raised."""
    p = tmp_path / "bad.txt"
    p.write_text(
        "good\tni3\t10\n"
        "badline no tab\n"          # wrong field count
        "also\tbad\tnotanint\n"     # freq not int
        "ok2\tha\t20\n"
    )
    entries = list(_iter_user_words(p))
    assert entries == [("good", "ni3", 10), ("ok2", "ha", 20)]
    # warnings were logged
    assert any("expected 3" in r.message for r in caplog.records)
    assert any("not an int" in r.message for r in caplog.records)


def test_iter_user_words_missing_file() -> None:
    """Missing file yields zero entries, not an error."""
    entries = list(_iter_user_words(Path("/nonexistent/file.txt")))
    assert entries == []


def test_lexicon_persist_roundtrip(tmp_path) -> None:
    """Learned words are flushed to disk and reloaded on next startup."""
    from unittest.mock import MagicMock

    # Create a minimal config-like object.
    user_path = tmp_path / "user_words.txt"
    mock_config = MagicMock()
    mock_config.dict.search_paths = []          # no system dicts
    mock_config.dict.user_words_path = str(user_path)

    # First session: insert learned words.
    lex = Lexicon.load(mock_config)
    assert not user_path.exists()              # nothing to flush yet
    lex.add_user_word("ni3", "你", freq=10)
    lex.add_user_word("hao3", "好", freq=5)
    lex._flush_now()
    assert user_path.exists()

    # Second session: same config, lexicon loads from disk.
    mock_config2 = MagicMock()
    mock_config2.dict.search_paths = []
    mock_config2.dict.user_words_path = str(user_path)
    lex2 = Lexicon.load(mock_config2)

    # User words from disk should be boosted (freq=10 and freq=5).
    ni3_entries = {e.word: e.freq for e in lex2.pinyin.lookup("ni3")}
    assert ni3_entries.get("你", 0) > 0   # at least some freq
    hao3_entries = {e.word: e.freq for e in lex2.pinyin.lookup("hao3")}
    assert hao3_entries.get("好", 0) > 0


def test_lexicon_flush_atomic(tmp_path) -> None:
    """Flush writes to a temp file then atomically renames, never leaving garbage."""
    from unittest.mock import MagicMock

    user_path = tmp_path / "user_words.txt"
    mock_config = MagicMock()
    mock_config.dict.search_paths = []
    mock_config.dict.user_words_path = str(user_path)

    lex = Lexicon.load(mock_config)
    lex.add_user_word("ni3", "你", freq=10)
    lex._flush_now()

    # No .tmp file left behind.
    assert not any(tmp_path.glob("*.tmp"))
    # Content is correct.
    lines = user_path.read_text(encoding="utf-8")
    assert "你" in lines
    assert "ni3" in lines


def test_lexicon_flush_idempotent(tmp_path) -> None:
    """Flushing when not dirty is a no-op (no error)."""
    from unittest.mock import MagicMock

    user_path = tmp_path / "user_words.txt"
    mock_config = MagicMock()
    mock_config.dict.search_paths = []
    mock_config.dict.user_words_path = str(user_path)

    lex = Lexicon.load(mock_config)
    lex._dirty = False
    lex._flush_now()   # should not raise even with no path
    assert not user_path.exists()


def test_lexicon_flush_no_path() -> None:
    """_flush_now with _user_words_path=None is a silent no-op."""
    from unittest.mock import MagicMock

    mock_config = MagicMock()
    mock_config.dict.search_paths = []
    mock_config.dict.user_words_path = "/nonexistent/path.txt"

    lex = Lexicon.load(mock_config)
    lex._dirty = True
    # No user_words_path set because file doesn't exist and wasn't created.
    lex._user_words_path = None
    lex._flush_now()   # must not raise
    assert lex._dirty  # still dirty since nothing was flushed
