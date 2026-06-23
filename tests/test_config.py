"""Tests for config._merge() — the type-validated config merge helper.

These regression tests cover the bugs that have crashed ibus-engine-tux-im
on startup more than once:

  1. PEP 563 (`from __future__ import annotations`) makes field annotations
     into strings, so reading `__dataclass_fields__[k].type` directly gives
     back a string and `isinstance(v, expected_type)` blows up with
     "TypeError: isinstance() arg 2 must be a type, ...".

  2. Generic containers like `list[str]` need their inner type checked too;
     `isinstance([1,2], (str,))` is False even for a valid list (because
     list is not a str subclass).

Each test below covers one of the field shapes declared in
``tux_im.config.config``.
"""

from __future__ import annotations

# tux_im.config.config uses `from __future__ import annotations`, so this
# is the same condition the production code runs under.
from tux_im.config.config import (
    Config,
    DictSection,
    IMESection,
    _merge,
)


def test_merge_plain_str_and_int() -> None:
    m = _merge(IMESection(), {"default_mode": "wbpy", "max_candidates": 9})
    assert m.default_mode == "wbpy"
    assert m.max_candidates == 9


def test_merge_wrong_type_is_dropped(caplog: object) -> None:
    # max_candidates is int; a string must be silently dropped (warning).
    caplog = caplog  # type: ignore[assignment]
    m = _merge(IMESection(), {"max_candidates": "nine"})  # type: ignore[arg-type]
    assert m.max_candidates == 9  # default preserved


def test_merge_unknown_field_is_dropped() -> None:
    m = _merge(IMESection(), {"nonexistent_key": 1})
    assert not hasattr(m, "nonexistent_key") or m.nonexistent_key != 1  # type: ignore[attr-defined]


def test_merge_bool_field() -> None:
    m = _merge(IMESection(), {"auto_punct": False})
    assert m.auto_punct is False


def test_merge_list_str_accepts_list_of_str() -> None:
    d = _merge(DictSection(), {"search_paths": ["/a", "/b"]})
    assert d.search_paths == ["/a", "/b"]


def test_merge_list_str_rejects_list_of_int() -> None:
    d = _merge(DictSection(), {"search_paths": [1, 2]})  # type: ignore[list-item]
    # Inner type check fails; field keeps its default.
    import os
    assert d.search_paths == [
        "/usr/share/rime-data",
        f"{os.path.expanduser('~')}/.config/tux-im/dicts",
        "./data",
    ]


def test_merge_all_sections_load() -> None:
    """Config.load() is the entry point that crashed in the wild. Smoke-test
    that loading with a non-existent path returns defaults and doesn't raise.
    """
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        cfg = Config.load(Path(td) / "missing.toml")
    assert cfg.ime.default_mode == "pinyin"
    assert cfg.dictionary.learn_enabled is True
