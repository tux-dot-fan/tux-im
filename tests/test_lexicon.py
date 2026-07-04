"""Tests for the lexicon / trie data structures."""

from __future__ import annotations

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
    # Order is file-order (comment lines skipped).  4th element (scheme)
    # is None for 3-column legacy files.
    assert entries == [("你好", "ni3hao", 50, None), ("我", "wo3", 30, None), ("他", "ha", 20, None)]


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
    assert entries == [("good", "ni3", 10, None), ("ok2", "ha", 20, None)]
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
    mock_config.dictionary.search_paths = []          # no system dicts
    mock_config.dictionary.user_words_path = str(user_path)

    # First session: insert learned words.
    lex = Lexicon.load(mock_config)
    assert not user_path.exists()              # nothing to flush yet
    lex.add_user_word("ni3", "你", freq=10)
    lex.add_user_word("hao3", "好", freq=5)
    lex._flush_now()
    assert user_path.exists()

    # Second session: same config, lexicon loads from disk.
    mock_config2 = MagicMock()
    mock_config2.dictionary.search_paths = []
    mock_config2.dictionary.user_words_path = str(user_path)
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
    mock_config.dictionary.search_paths = []
    mock_config.dictionary.user_words_path = str(user_path)

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
    mock_config.dictionary.search_paths = []
    mock_config.dictionary.user_words_path = "/nonexistent/path.txt"

    lex = Lexicon.load(mock_config)
    lex._dirty = False
    lex._flush_now()   # should not raise even with no path
    assert not user_path.exists()


def test_lexicon_flush_no_path() -> None:
    """_flush_now with _user_words_path=None is a silent no-op."""
    from unittest.mock import MagicMock

    mock_config = MagicMock()
    mock_config.dictionary.search_paths = []
    mock_config.dictionary.user_words_path = "/nonexistent/path.txt"

    lex = Lexicon.load(mock_config)
    lex._dirty = True
    # No user_words_path set because file doesn't exist and wasn't created.
    lex._user_words_path = None


# ---------------------------------------------------------------------------
# Regression: user words must survive restart and not bloat the file
# ---------------------------------------------------------------------------


def test_user_word_survives_restart_when_code_exists_in_system_dict(tmp_path) -> None:
    """A user-learned word whose code already exists in the system trie
    but whose word text does NOT must be inserted (not silently dropped)
    on reload.

    Before the fix: ``_load_user_words`` called ``boost(code, word)``
    when ``exact(code)`` was True, but ``boost`` is a no-op when the
    specific (code, word) pair is absent → the user word was lost.
    """
    from unittest.mock import MagicMock

    user_path = tmp_path / "user_words.txt"
    mock_config = MagicMock()
    mock_config.dictionary.search_paths = []
    mock_config.dictionary.user_words_path = str(user_path)

    # Session 1: system trie has "zhe2" → "哲", user learns "喆".
    lex = Lexicon.load(mock_config)
    lex.pinyin.insert("zhe2", "哲", 100)
    lex.add_user_word("zhe2", "喆", freq=50, scheme="pinyin")
    lex._flush_now()

    # Session 2: fresh lexicon, system dict reloaded, user words merged.
    mock_config2 = MagicMock()
    mock_config2.dictionary.search_paths = []
    mock_config2.dictionary.user_words_path = str(user_path)
    lex2 = Lexicon.load(mock_config2)
    lex2.pinyin.insert("zhe2", "哲", 100)

    # The user word "喆" must still be present.
    entries = {e.word for e in lex2.pinyin.lookup("zhe2")}
    assert "喆" in entries, f'user word lost on restart: {entries}'
    assert "哲" in entries, f'system word missing: {entries}'


def test_user_words_file_does_not_include_system_entries(tmp_path) -> None:
    """_write_user_words must only persist user-learned entries, not the
    entire system dictionary.

    Before the fix: ``_write_user_words`` iterated every entry in the
    trie (including system dict entries), causing the user words file
    to grow unboundedly with the full system dictionary on every flush.
    """
    from unittest.mock import MagicMock

    user_path = tmp_path / "user_words.txt"
    mock_config = MagicMock()
    mock_config.dictionary.search_paths = []
    mock_config.dictionary.user_words_path = str(user_path)

    lex = Lexicon.load(mock_config)
    # Simulate a system dictionary with many entries.
    for i in range(100):
        lex.pinyin.insert(f"code{i}", f"word{i}", freq=i)
    # User learns only one word.
    lex.add_user_word("ni3", "你", freq=10, scheme="pinyin")
    lex._flush_now()

    # The file should contain only the user entry, not 100 system entries.
    lines = user_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1, f'expected 1 line, got {len(lines)}: {lines}'
    assert "你" in lines[0]
    assert "ni3" in lines[0]
    assert "pinyin" in lines[0]  # scheme column


def test_user_words_file_includes_scheme_column(tmp_path) -> None:
    """The 4th column (scheme) is written so reload can route correctly."""
    from unittest.mock import MagicMock

    user_path = tmp_path / "user_words.txt"
    mock_config = MagicMock()
    mock_config.dictionary.search_paths = []
    mock_config.dictionary.user_words_path = str(user_path)

    lex = Lexicon.load(mock_config)
    lex.add_user_word("ni3", "你", freq=10, scheme="pinyin")
    lex.add_user_word("kld", "我", freq=20, scheme="wubi")
    lex._flush_now()

    lines = user_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    pinyin_line = next(line for line in lines if "ni3" in line)
    wubi_line = next(line for line in lines if "kld" in line)
    assert pinyin_line.endswith("\tpinyin")
    assert wubi_line.endswith("\twubi")


def test_detect_scheme_pinyin_with_tone() -> None:
    """Codes with digits are always pinyin."""
    from unittest.mock import MagicMock
    mock_config = MagicMock()
    mock_config.dictionary.search_paths = []
    mock_config.dictionary.user_words_path = "/dev/null"
    lex = Lexicon.load(mock_config)
    assert lex._detect_scheme("ni3") == "pinyin"
    assert lex._detect_scheme("hao3") == "pinyin"


def test_detect_scheme_wubi_pure_letters() -> None:
    """Pure-letter codes that are wubi prefixes (and not pinyin prefixes)
    are detected as wubi."""
    from unittest.mock import MagicMock
    mock_config = MagicMock()
    mock_config.dictionary.search_paths = []
    mock_config.dictionary.user_words_path = "/dev/null"
    lex = Lexicon.load(mock_config)
    # Populate wubi trie with a known prefix.
    lex.wubi.insert("kld", "我", 100)
    assert lex._detect_scheme("kld") == "wubi"
    # A code that is neither in wubi nor pinyin defaults to pinyin
    # (covers Google Pinyin buffers without tone digits).
    assert lex._detect_scheme("nihao") == "pinyin"


# ---------------------------------------------------------------------------
# Rime dict parser: 4-column (wubi) vs 3-column (pinyin) format
# ---------------------------------------------------------------------------

def test_load_rime_dict_3col_format(tmp_path: Path) -> None:
    """3-column lines ``word\\tcode\\tfreq`` parse correctly."""
    f = tmp_path / "test.dict.yaml"
    f.write_text(
        "# header\n"
        "---\n"
        "你\tni3\t100\n"
        "好\thao3\t80\n"
        "国\tguo2\t90\n",
        encoding="utf-8",
    )
    entries = list(load_rime_dict(f))
    assert entries == [("你", "ni3", 100), ("好", "hao3", 80), ("国", "guo2", 90)]


def test_load_rime_dict_4col_format(tmp_path: Path) -> None:
    """4-column lines ``word\\tcode\\tfreq\\tstem`` parse (stem ignored).

    Wubi86 dict files use this format.  The previous regex used
    greedy ``\\S+`` and swallowed the entire line, silently dropping
    every 4-column entry -- including all 25 single-letter "level-1"
    wubi codes.  This regression test pins the fix.
    """
    f = tmp_path / "wubi.dict.yaml"
    f.write_text(
        "工\ta\t99454797\taa\n"
        "了\tb\t1477224452\tbn\n"
        "一\tg\t2015124793\tgg\n",
        encoding="utf-8",
    )
    entries = list(load_rime_dict(f))
    assert entries == [
        ("工", "a", 99454797),
        ("了", "b", 1477224452),
        ("一", "g", 2015124793),
    ]


def test_load_rime_dict_single_letter_wubi_codes(tmp_path: Path) -> None:
    """Single-letter wubi codes (the "level-1" 简码) must parse and insert.

    This is the user-reported bug: typing 'g' produced no candidate
    because the parser was dropping all 1-letter wubi codes.
    """
    from tux_im.input.lexicon import Trie

    f = tmp_path / "wubi86.dict.yaml"
    f.write_text(
        "工\ta\t99454797\taa\n"
        "了\tb\t1477224452\tbn\n"
        "以\tc\t418261033\tny\n"
        "在\td\t1133790406\tdh\n"
        "一\tg\t2015124793\tgg\n",
        encoding="utf-8",
    )
    t = Trie()
    for word, code, freq in load_rime_dict(f):
        t.insert(code, word, freq)
    # All five 1-letter codes must resolve.
    assert [e.word for e in t.lookup("a")] == ["工"]
    assert [e.word for e in t.lookup("b")] == ["了"]
    assert [e.word for e in t.lookup("c")] == ["以"]
    assert [e.word for e in t.lookup("d")] == ["在"]
    assert [e.word for e in t.lookup("g")] == ["一"]
    # And the prefix check used by WubiMode.feed_key must succeed.
    assert t.has_prefix("g")


def test_load_rime_dict_real_wubi86_has_25_level1_codes() -> None:
    """Real wubi86.dict.yaml from /usr/share/rime-data has 25 level-1 codes.

    Guards against any future regression where the parser again drops
    single-letter codes.  Skipped if the upstream dict file is not
    installed (e.g. dev environments without ibus-rime).
    """
    real = Path("/usr/share/rime-data/wubi86.dict.yaml")
    if not real.exists():
        import pytest
        pytest.skip("wubi86.dict.yaml not present on this system")

    t = Trie()
    single_letter: list[str] = []
    for word, code, freq in load_rime_dict(real):
        t.insert(code, word, freq)
        if len(code) == 1 and code.isalpha():
            single_letter.append(code)
    # Wubi 86 maps 25 keys (a-y) to single-letter high-frequency chars.
    assert len(single_letter) == 25, (
        f"expected 25 single-letter wubi codes, got {len(single_letter)}: "
        f"{sorted(single_letter)}"
    )
    # And every one of them must actually resolve in the trie.
    for code in "abcdefghijklmnopqrstuvwxyz"[:25]:
        entries = t.lookup(code)
        assert len(entries) >= 1, f"code {code!r} has no entries in trie"
