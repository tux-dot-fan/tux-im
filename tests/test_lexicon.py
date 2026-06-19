"""Tests for the lexicon / trie data structures."""

from __future__ import annotations

from tux_im.input.lexicon import Trie, load_rime_dict


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
