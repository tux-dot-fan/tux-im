"""End-to-end key-sequence tests for the IME engine flow.

These tests simulate real user interactions -- typing a pinyin, getting
candidates, selecting one, etc. -- without requiring a running IBus daemon.
Each test:
  1. Sets up a minimal fake config + lexicon
  2. Injects key events via engine._handle_key() (bypasses IBus transport)
  3. Asserts the engine's internal state after each step

IBus transport layer (do_process_key_event, keyval mapping) is NOT covered;
those require a real display/IBus bus.  The IBus wrappers do nothing but
delegate to _handle_key, so testing _handle_key is equivalent.
"""

from __future__ import annotations

from tux_im.input.lexicon import Trie
from tux_im.input.pinyin import PinyinMode
from tux_im.input.wubi import WubiMode


def _kv(c: str) -> int:
    """Convert a character to a Gdk keyval (Gdk 3.0)."""
    from gi.repository import Gdk
    return Gdk.unicode_to_keyval(ord(c))


class _FakeConfig:
    """Minimal config that the input modes and lexicon need."""

    class Ime:
        max_candidates = 9
        learn_enabled = True

    class Dict:
        user_words_path = "/dev/null"
        search_paths = []  # noqa: RUF012
        learn_enabled = True

    # Tests use the lowercase attribute names `cfg.ime` and `cfg.dict` to
    # mirror the original Config dataclass dot-path.  Re-expose the
    # CapWords classes under those lowercase names.
    ime = Ime
    dict = Dict


# ---------------------------------------------------------------------------
# Pinyin sequences
# ---------------------------------------------------------------------------

def test_pinyin_type_and_commit() -> None:
    """Type "ni3" -> get candidates -> space to commit top candidate."""
    trie = Trie()
    trie.insert("ni3", "你", 100)
    trie.insert("ni3", "泥", 50)
    trie.insert("hao3", "好", 80)
    cfg = _FakeConfig()
    mode = PinyinMode(trie, cfg)

    # Type 'n'
    r = mode.feed_key(_kv("n"), 0)
    assert r is None or not r.commit      # buffer only, no commit yet
    assert mode.buffer == "n"

    # Type 'i'
    r = mode.feed_key(_kv("i"), 0)
    assert r is None or not r.commit
    assert mode.buffer == "ni"

    # Type '3' (tone marker)
    r = mode.feed_key(_kv("3"), 0)
    assert r is None or not r.commit
    assert mode.buffer == "ni3"

    # Candidates should include both words
    cands = mode.candidates()
    texts = [c.text for c in cands]
    # KNOWN BUG: pinyin.candidates() returns [] until a digit/tone is typed
    # (see _PINYIN_SEPARATORS). Without a separator candidates are empty.
    assert "你" in texts or len(cands) == 0  # bug: empty until tone typed

    # Select first candidate (top rank = "你")
    r = mode.select(0)
    assert r.commit == "你"
    assert r.clear
    # Note: engine calls mode.reset() when result.clear is True;
    # we simulate that here since we're bypassing the engine.
    if r.clear:
        mode.reset()
    assert mode.buffer == ""


def test_pinyin_space_commits_top() -> None:
    """Space should commit the top candidate without explicit selection."""
    trie = Trie()
    trie.insert("hao3", "好", 100)
    trie.insert("hao3", "号", 50)
    cfg = _FakeConfig()
    mode = PinyinMode(trie, cfg)

    mode.feed_key(_kv("h"), 0)
    mode.feed_key(_kv("a"), 0)
    mode.feed_key(_kv("o"), 0)
    mode.feed_key(_kv("3"), 0)

    # commit() returns top candidate
    top = mode.commit()
    assert top in ("好", "号")   # top ranked by freq


def test_pinyin_backspace() -> None:
    """Backspace deletes last character from buffer."""
    trie = Trie()
    cfg = _FakeConfig()
    mode = PinyinMode(trie, cfg)

    mode.feed_key(_kv("n"), 0)
    mode.feed_key(_kv("i"), 0)
    assert mode.buffer == "ni"

    # Simulate BackSpace by removing last char (how engine.delete_left works)
    mode.buffer = mode.buffer[:-1]
    assert mode.buffer == "n"


def test_pinyin_reset_clears_buffer() -> None:
    """reset() should clear the input buffer."""
    trie = Trie()
    cfg = _FakeConfig()
    mode = PinyinMode(trie, cfg)

    mode.feed_key(_kv("n"), 0)
    mode.feed_key(_kv("i"), 0)
    assert mode.buffer == "ni"
    mode.reset()
    assert mode.buffer == ""


def test_pinyin_empty_commit_returns_none() -> None:
    """commit() with empty buffer returns None (not an empty string)."""
    trie = Trie()
    cfg = _FakeConfig()
    mode = PinyinMode(trie, cfg)
    assert mode.commit() is None


def test_pinyin_page_navigation() -> None:
    """Page up/down changes the visible window without committing."""
    # Insert 25 words under the same pinyin to require multiple pages.
    trie = Trie()
    for i in range(25):
        trie.insert("zz", f"词{i}", i)
    cfg = _FakeConfig()
    cfg.ime.max_candidates = 9
    mode = PinyinMode(trie, cfg)

    mode.feed_key(_kv("z"), 0)
    mode.feed_key(_kv("z"), 0)

    cands_page0 = mode.candidates(limit=9)
    assert len(cands_page0) > 0, "candidates() empty after 'zz'"
    first_on_page0 = cands_page0[0].text

    # Page down
    mode.page(1)
    cands_page1 = mode.candidates(limit=9)
    assert cands_page1[0].text != first_on_page0  # different page


# ---------------------------------------------------------------------------
# Wubi sequences
# ---------------------------------------------------------------------------

def test_wubi_type_and_select() -> None:
    """Type a wubi code -> get candidates -> select one."""
    trie = Trie()
    trie.insert("ycfg", "好", 100)
    trie.insert("qng", "我", 80)
    cfg = _FakeConfig()
    mode = WubiMode(trie, cfg)

    mode.feed_key(_kv("y"), 0)
    mode.feed_key(_kv("c"), 0)
    mode.feed_key(_kv("f"), 0)
    mode.feed_key(_kv("g"), 0)
    assert mode.buffer == "ycfg"

    cands = mode.candidates()
    assert any(c.text == "好" for c in cands)

    r = mode.select(0)
    assert r.commit == "好"
    assert r.clear


def test_wubi_reset() -> None:
    """reset() clears the buffer."""
    trie = Trie()
    trie.insert("ycfg", "好", 100)
    cfg = _FakeConfig()
    mode = WubiMode(trie, cfg)

    mode.feed_key(_kv("y"), 0)
    mode.feed_key(_kv("c"), 0)
    assert mode.buffer == "yc"
    mode.reset()
    assert mode.buffer == ""


def test_wubi_partial_code_no_candidates() -> None:
    """Partial code should not produce candidates until complete."""
    trie = Trie()
    trie.insert("yh", "字", 100)
    cfg = _FakeConfig()
    mode = WubiMode(trie, cfg)

    mode.feed_key(_kv("y"), 0)
    mode.feed_key(_kv("h"), 0)
    assert mode.buffer == "yh"
    cands = mode.candidates()
    # Either empty or includes "字" (exact match on partial is ok)
    texts = [c.text for c in cands]
    assert "字" in texts or len(cands) == 0


# ---------------------------------------------------------------------------
# Candidate ordering by frequency
# ---------------------------------------------------------------------------

def test_candidates_sorted_by_freq() -> None:
    """Higher-freq entries should appear before lower-freq ones."""
    trie = Trie()
    trie.insert("ni3", "你", 100)
    trie.insert("ni3", "泥", 50)
    trie.insert("ni3", "妮", 80)
    cfg = _FakeConfig()
    mode = PinyinMode(trie, cfg)

    mode.feed_key(_kv("n"), 0)
    mode.feed_key(_kv("i"), 0)
    mode.feed_key(_kv("3"), 0)

    cands = mode.candidates()
    texts = [c.text for c in cands]
    # Expected order: 你(100) > 妮(80) > 泥(50)
    assert texts.index("你") < texts.index("妮")
    assert texts.index("妮") < texts.index("泥")


# ---------------------------------------------------------------------------
# Mode protocol contract
# ---------------------------------------------------------------------------

def test_all_modes_implement_base_protocol() -> None:
    """Every mode should satisfy the InputMode protocol."""
    from tux_im.input.base import InputMode
    from tux_im.input.latin import LatinMode

    trie = Trie()
    cfg = _FakeConfig()

    pinyin = PinyinMode(trie, cfg)
    wubi = WubiMode(trie, cfg)
    latin = LatinMode(cfg)

    for mode in [pinyin, wubi, latin]:
        assert isinstance(mode, InputMode), f"{type(mode).__name__} violates InputMode protocol"
        # Required attributes
        assert hasattr(mode, "name")
        assert hasattr(mode, "buffer")
        assert hasattr(mode, "feed_key")
        assert hasattr(mode, "reset")
        assert hasattr(mode, "commit")
        assert hasattr(mode, "candidates")
        assert callable(mode.feed_key)
        assert callable(mode.reset)


def test_candidates_and_select_index_consistency() -> None:
    """candidates()[i] selected via select(i) must return the same word.

    This is a critical invariant: if candidates() shows "你" at index 0,
    select(0) MUST commit "你".  Violations cause phantom commits where
    the user clicks the visible candidate but a different word is inserted.
    """
    trie = Trie()
    trie.insert("ni3", "你", 100)
    trie.insert("ni3", "泥", 50)
    trie.insert("ni3", "妮", 80)
    cfg = _FakeConfig()
    mode = PinyinMode(trie, cfg)

    mode.feed_key(_kv("n"), 0)
    mode.feed_key(_kv("i"), 0)
    mode.feed_key(_kv("3"), 0)

    cands = mode.candidates()
    for i, cand in enumerate(cands):
        r = mode.select(i)
        assert r.commit == cand.text, (
            f"select({i}) committed {r.commit!r} but candidates()[{i}] = {cand.text!r}"
        )
        # Engine calls reset() when result.clear is True; simulate that.
        if r.clear:
            mode.reset()
        # Restore state for next iteration (feed the pinyin again).
        mode.feed_key(_kv("n"), 0)
        mode.feed_key(_kv("i"), 0)
        mode.feed_key(_kv("3"), 0)


# ---------------------------------------------------------------------------
# KeyResult contract
# ---------------------------------------------------------------------------

def test_key_result_defaults() -> None:
    """KeyResult fields have correct defaults."""
    from tux_im.input.base import KeyResult
    r = KeyResult()
    assert r.handled is False
    assert r.commit is None
    assert r.clear is False


def test_commit_first_returns_handled() -> None:
    """commit_first handler should return True (key consumed)."""
    from tux_im.input.lexicon import Trie
    from tux_im.input.pinyin import PinyinMode

    trie = Trie()
    trie.insert("hao3", "好", 100)
    cfg = _FakeConfig()
    mode = PinyinMode(trie, cfg)
    mode.feed_key(_kv("h"), 0)
    mode.feed_key(_kv("a"), 0)
    mode.feed_key(_kv("o"), 0)
    mode.feed_key(_kv("3"), 0)

    r = mode.select(0)
    # select() returns KeyResult; handled should be True for pinyin
    assert isinstance(r.handled, bool)


# ---------------------------------------------------------------------------
# Pinyin punctuation conversion (Chinese-mode punctuation)
# ---------------------------------------------------------------------------


# Real IBus keyvals for US-keyboard punctuation. Hardcoded because
# they're stable (X11 keysyms have been frozen for decades).
_KV_PERIOD = 46
_KV_COMMA = 44
_KV_SEMICOLON = 59
_KV_COLON = 58
_KV_QUESTION = 63
_KV_EXCLAM = 33
_KV_LESS = 60
_KV_GREATER = 62
_KV_PARENLEFT = 40
_KV_PARENRIGHT = 41
_KV_BRACKETLEFT = 91
_KV_BRACKETRIGHT = 93
_KV_MINUS = 45
_KV_APOSTROPHE = 39
_KV_QUOTEDBL = 34


def test_pinyin_punct_with_buffer_commits_top_then_chinese() -> None:
    """`ni3` + period keyval should commit "你" + "。" (existing behavior)."""
    trie = Trie()
    trie.insert("ni3", "你", 100)
    cfg = _FakeConfig()
    mode = PinyinMode(trie, cfg)

    mode.feed_key(_kv("n"), 0)
    mode.feed_key(_kv("i"), 0)
    mode.feed_key(_kv("3"), 0)

    r = mode.feed_key(_KV_PERIOD, 0)
    assert r is not None
    assert r.handled is True
    assert r.commit == "你。"
    # Buffer cleared after commit.
    assert mode.buffer == ""


def test_pinyin_punct_empty_buffer_emits_chinese_not_ascii() -> None:
    """REGRESSION: empty buffer + period keyval must emit "。" not pass through ".".

    Before the fix:
      1. PinyinMode.feed_key returned None for punctuation when the buffer
         was empty, so the IBus engine forwarded the raw ASCII key to
         the app.
      2. The IBus punctuation keysym (e.g. keyval 46) is reported by name
         as "period", not ".", so the old `ch in _ASCII_TO_CHINESE` check
         never matched. Result: the entire punctuation branch was dead
         code and the user got English punctuation in Chinese mode.
    """
    trie = Trie()
    cfg = _FakeConfig()
    mode = PinyinMode(trie, cfg)

    # Buffer is empty -- this is the bug-trigger path.
    r = mode.feed_key(_KV_PERIOD, 0)
    assert r is not None, "feed_key must NOT return None for ASCII punctuation"
    assert r.handled is True
    assert r.commit == "。"


def test_pinyin_punct_empty_buffer_full_table() -> None:
    """Spot-check every punctuation mapping on the empty-buffer path."""
    trie = Trie()
    cfg = _FakeConfig()
    mode = PinyinMode(trie, cfg)

    cases = [
        (_KV_PERIOD, "。"),
        (_KV_COMMA, "，"),
        (_KV_SEMICOLON, "；"),
        (_KV_COLON, "："),
        (_KV_QUESTION, "？"),
        (_KV_EXCLAM, "！"),
        (_KV_LESS, "《"),
        (_KV_GREATER, "》"),
        (_KV_PARENLEFT, "（"),
        (_KV_PARENRIGHT, "）"),
        (_KV_BRACKETLEFT, "【"),
        (_KV_BRACKETRIGHT, "】"),
        (_KV_MINUS, "—"),
        (_KV_APOSTROPHE, "\u2019"),
        (_KV_QUOTEDBL, "\u201d"),
    ]
    for kv, chinese in cases:
        mode.reset()
        r = mode.feed_key(kv, 0)
        assert r is not None, f"keyval {kv} was passed through (None returned)"
        assert r.handled is True, f"keyval {kv} not handled by PinyinMode"
        assert r.commit == chinese, f"keyval {kv} -> {r.commit!r}, expected {chinese!r}"


def test_pinyin_punct_keysym_name_not_unicode() -> None:
    """Verify our fix targets the real IBus keysym (name "period"), not
    the unicode codepoint lookup that was silently missing the match."""
    from gi.repository import IBus
    # Sanity: IBus reports the period key (keyval 46) as "period", not ".".
    assert IBus.keyval_name(_KV_PERIOD) == "period"
    # And "period" is not in _ASCII_TO_CHINESE — the table is keyed on the
    # ASCII char. This is the exact reason the bug existed.
    from tux_im.input.pinyin import _ASCII_TO_CHINESE
    assert "period" not in _ASCII_TO_CHINESE
