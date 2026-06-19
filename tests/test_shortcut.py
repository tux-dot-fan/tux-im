"""Tests for the shortcut parser."""

from __future__ import annotations

import pytest

from tux_im.shortcut import parse_shortcut


def test_parse_simple_key() -> None:
    p = parse_shortcut("space")
    assert p.keyval != 0


def test_parse_ctrl_modifier() -> None:
    p = parse_shortcut("<Ctrl>g")
    assert p.keyval != 0
    assert p.modifiers != 0


def test_parse_multiple_modifiers() -> None:
    p = parse_shortcut("<Ctrl><Shift>m")
    assert p.keyval != 0
    assert p.modifiers != 0


def test_parse_invalid() -> None:
    with pytest.raises(ValueError):
        parse_shortcut("")
    with pytest.raises(ValueError):
        parse_shortcut("NotAKeyName12345")
