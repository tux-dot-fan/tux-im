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
    """The default `page_up` binding includes `-` (Rime-style minus for
    paging up) so users can use the keyboard shortcut for navigating
    to the previous page of candidates.

    Following Rime convention (`paging_with_minus_equal` in
    rime-prelude/key_bindings.yaml), only `minus` is bound to page_up;
    `plus` is NOT a page key because the Rime-style convention is to
    let `plus` always emit its fullwidth Chinese equivalent `＋`.
    """
    section = ShortcutSection()
    assert "minus" in section.page_up
    assert "bracketleft" in section.page_up


def test_page_down_default_includes_equal() -> None:
    """The default `page_down` binding includes `=` (Rime-style equal
    for paging down) but NOT `plus` -- `plus` is reserved for the
    fullwidth Chinese mapping `＋`, per Rime convention.
    """
    section = ShortcutSection()
    assert "equal" in section.page_down
    assert "bracketright" in section.page_down
    assert "plus" not in section.page_down


def test_shortcut_manager_routes_all_aliases_to_same_action() -> None:
    """ShortcutManager.rebuild binds every spec in a list to the same action.

    Pressing `[` and `-` should both trigger `page_up`.  Pressing `]`
    and `=` should both trigger `page_down`.  The manager dispatches by
    key, not by handler; the handler itself is registered separately by
    the engine, so we just assert the binding was created for each alias.
    """
    import gi
    gi.require_version("IBus", "1.0")
    from gi.repository import IBus

    cfg_section = ShortcutSection()
    class _Cfg:
        shortcuts = cfg_section
    mgr = ShortcutManager(_Cfg())  # type: ignore[arg-type]
    bound: dict[str, set[str]] = {}
    for parsed, action in mgr._bindings:  # type: ignore[attr-defined]
        bound.setdefault(action, set()).add(
            IBus.keyval_name(parsed.keyval) or ""
        )
    # page_up
    assert "bracketleft" in bound["page_up"]
    assert "minus" in bound["page_up"]
    # page_down
    assert "bracketright" in bound["page_down"]
    assert "equal" in bound["page_down"]
    # plus is NOT a page key in the Rime convention
    assert "plus" not in bound["page_up"]
    assert "plus" not in bound["page_down"]


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
