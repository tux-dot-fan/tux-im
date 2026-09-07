"""Tests for the shortcut parser and multi-key binding support."""

from __future__ import annotations

import pytest

from tux_im.config.config import ShortcutSection, _merge
from tux_im.shortcut import ShortcutManager, parse_shortcut


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
    with pytest.raises(ValueError, match="empty shortcut spec"):
        parse_shortcut("")
    with pytest.raises(ValueError, match="unknown key name"):
        parse_shortcut("NotAKeyName12345")


def test_parse_plus_minus_equal() -> None:
    """`+` (plus, Shift+=), `-` (minus), and `=` (equal) all parse to valid keysyms.

    These are the keys users expect to use for candidate page navigation on a
    US keyboard layout.  `plus` requires Shift, but `equal` is the unshifted
    form of the same physical key — both must be bindable.
    """
    for spec in ("plus", "minus", "equal"):
        p = parse_shortcut(spec)
        assert p.keyval != 0, f"{spec!r} did not resolve to a keyval"


def test_page_up_default_includes_minus() -> None:
    """The default `page_up` binding includes `-` so users can use it for
    moving to the previous page of candidates."""
    section = ShortcutSection()
    assert "minus" in section.page_up
    assert "bracketleft" in section.page_up


def test_page_down_default_includes_plus_and_equal() -> None:
    """The default `page_down` binding includes both `+` (Shift+=) and the
    bare `=` key so users on a US keyboard can use either spelling."""
    section = ShortcutSection()
    assert "plus" in section.page_down
    assert "equal" in section.page_down
    assert "bracketright" in section.page_down


def test_shortcut_manager_routes_all_aliases_to_same_action() -> None:
    """ShortcutManager.rebuild binds every spec in a list to the same action.

    Pressing `+`, `=`, or `]` should all trigger the action registered for
    `page_down`.  The manager dispatches by key, not by handler; the
    handler itself is registered separately by the engine, so we just
    assert the binding was created for each alias.
    """
    import gi
    gi.require_version("IBus", "1.0")
    from gi.repository import IBus

    cfg_section = ShortcutSection()
    class _Cfg:
        shortcuts = cfg_section
    mgr = ShortcutManager(_Cfg())  # type: ignore[arg-type]
    bound_keysyms: dict[str, int] = {}
    for parsed, action in mgr._bindings:  # type: ignore[attr-defined]
        if action == "page_down":
            bound_keysyms[IBus.keyval_name(parsed.keyval) or ""] = parsed.keyval
    assert "plus" in bound_keysyms
    assert "equal" in bound_keysyms
    assert "bracketright" in bound_keysyms


def test_merge_wraps_single_string_into_list() -> None:
    """A config file written before page_up/page_down became multi-key
    may still have ``page_up = "bracketleft"`` (str, not list).  _merge must
    wrap that into a one-element list so the user does not silently lose
    the alias list."""
    section = ShortcutSection()
    data = {"page_up": "bracketleft", "page_down": "equal"}
    merged = _merge(section, data)
    assert merged.page_up == ["bracketleft"]
    assert merged.page_down == ["equal"]
