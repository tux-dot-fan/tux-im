"""Floating, no-focus overlay window for voice input."""

from __future__ import annotations

import logging
import math
from enum import StrEnum

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

log = logging.getLogger(__name__)

_PI_2 = math.pi / 2


class OverlayState(StrEnum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    RESULT = "result"


class OverlayWindow:
    """A small popup window with no focus, positioned near the cursor.

    Designed to show:
    - a mic icon + state
    - an audio level meter
    - the live or final transcript
    - ASR alternatives
    - action buttons
    """

    def __init__(self) -> None:
        self.win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.win.set_decorated(False)
        self.win.set_accept_focus(False)
        self.win.set_focus_on_map(False)
        self.win.set_skip_taskbar_hint(True)
        self.win.set_skip_pager_hint(True)
        self.win.set_keep_above(True)
        self.win.set_app_paintable(True)
        self.win.set_default_size(360, 80)

        # Visual: rounded box with border.
        screen = self.win.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.win.set_visual(visual)
        self.win.connect("draw", self._on_draw)

        # Content layout.
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_border_width(8)

        # Header row: icon + state label + close button.
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._icon = Gtk.Label(label="🎤")
        self._state_label = Gtk.Label(label="按 Ctrl+` 开始")
        self._state_label.set_xalign(0)
        self._close = Gtk.Button(label="✕")
        self._close.set_relief(Gtk.ReliefStyle.NONE)
        self._close.connect("clicked", lambda *_: self.hide())
        header.pack_start(self._icon, False, False, 0)
        header.pack_start(self._state_label, True, True, 0)
        header.pack_end(self._close, False, False, 0)
        vbox.pack_start(header, False, False, 0)

        # Level meter (just a thin bar).
        self._level = Gtk.ProgressBar()
        self._level.set_fraction(0.0)
        vbox.pack_start(self._level, False, False, 0)

        # Transcript / alternatives.
        self._text = Gtk.Label(label="")
        self._text.set_xalign(0)
        self._text.set_line_wrap(True)
        self._text.set_selectable(True)
        vbox.pack_start(self._text, True, True, 0)

        self._alts = Gtk.Label(label="")
        self._alts.set_xalign(0)
        self._alts.set_line_wrap(True)
        vbox.pack_start(self._alts, False, False, 0)

        # Footer hints.
        self._footer = Gtk.Label(label="")
        self._footer.set_xalign(0)
        vbox.pack_start(self._footer, False, False, 0)

        self.win.add(vbox)
        self._state: OverlayState = OverlayState.IDLE

    # ---- public API ----

    def show_at_cursor(self) -> None:
        display = Gdk.Display.get_default()
        seat = display.get_default_seat() if display else None
        pointer = seat.get_pointer() if seat else None
        if pointer is not None:
            _, x, y = pointer.get_position()
        else:
            x, y = 200, 200
        self.win.move(x + 12, y + 24)
        self.win.show_all()
        # Re-assert no-focus on map.
        self.win.set_accept_focus(False)

    def hide(self) -> None:
        self.win.hide()
        self._state = OverlayState.IDLE

    def set_state(self, state: OverlayState, text: str = "") -> None:
        self._state = state
        mapping = {
            OverlayState.IDLE: ("💤", "空闲"),
            OverlayState.RECORDING: ("🎙️", "正在聆听..."),
            OverlayState.PROCESSING: ("⏳", "识别中..."),
            OverlayState.RESULT: ("📝", "识别结果"),
        }
        icon, label = mapping[state]
        self._icon.set_text(icon)
        self._state_label.set_text(label)
        self._text.set_text(text or "")
        if state == OverlayState.RESULT:
            self._footer.set_text("⏎ 发送  Tab 切换候选  Esc 取消")
        elif state == OverlayState.RECORDING:
            self._footer.set_text("再按一次 Ctrl+` 结束")
        elif state == OverlayState.PROCESSING:
            self._footer.set_text("请稍候...")
        else:
            self._footer.set_text("")

    def set_level(self, fraction: float) -> None:
        self._level.set_fraction(max(0.0, min(1.0, fraction)))

    def set_alternatives(self, alts: list[str]) -> None:
        if not alts:
            self._alts.set_text("")
            return
        rendered = "  ·  ".join(f"[{i+1}] {a}" for i, a in enumerate(alts[:5]))
        self._alts.set_text(rendered)

    def get_transcript(self) -> str:
        return str(self._text.get_text())

    def set_transcript(self, text: str) -> None:
        self._text.set_text(text)

    # ---- internals ----

    def _on_draw(self, widget: Gtk.Widget, cr: object) -> bool:  # type: ignore[type-arg]
        # Rounded background.
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        r = 8
        cr.new_sub_path()
        cr.arc(w - r, r, r, -_PI_2, 0)
        cr.arc(w - r, h - r, r, 0, _PI_2)
        cr.arc(r, h - r, r, _PI_2, math.pi)
        cr.arc(r, r, r, math.pi, 3 * _PI_2)
        cr.close_path()
        cr.set_source_rgba(0.1, 0.1, 0.12, 0.92)
        cr.fill_preserve()
        cr.set_source_rgba(0.4, 0.4, 0.5, 0.9)
        cr.set_line_width(1)
        cr.stroke()
        return False

