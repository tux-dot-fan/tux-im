"""Settings panel for TUX IM (runs as `tux-im-setup`)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from tux_im.config.config import Config

log = logging.getLogger(__name__)

MODES = ["pinyin", "wubi", "wbpy"]


class SettingsWindow:
    """A `Gtk.Window` with a notebook of settings tabs."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self.win = Gtk.Window(title="TUX IM 设置")
        self.win.set_default_size(560, 420)
        self.win.set_border_width(8)
        self.win.connect("destroy", Gtk.main_quit)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.win.add(vbox)

        notebook = Gtk.Notebook()
        vbox.pack_start(notebook, True, True, 0)

        notebook.append_page(self._build_ime_tab(), Gtk.Label(label="输入法"))
        notebook.append_page(self._build_shortcuts_tab(), Gtk.Label(label="快捷键"))
        notebook.append_page(self._build_asr_tab(), Gtk.Label(label="语音"))
        notebook.append_page(self._build_appearance_tab(), Gtk.Label(label="外观"))
        notebook.append_page(self._build_about_tab(), Gtk.Label(label="关于"))

        # Bottom buttons.
        bbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bbox.set_halign(Gtk.Align.END)
        reset = Gtk.Button(label="重置默认")
        reset.connect("clicked", self._on_reset)
        save = Gtk.Button(label="保存")
        save.connect("clicked", self._on_save)
        bbox.add(reset)
        bbox.add(save)
        vbox.pack_start(bbox, False, False, 0)

    # ---- builders ----

    def _build_ime_tab(self) -> Gtk.Box:
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_border_width(16)

        grid.attach(Gtk.Label(label="默认模式:", xalign=1), 0, 0, 1, 1)
        self._mode_combo = Gtk.ComboBoxText()
        for m in MODES:
            self._mode_combo.append_text(m)
        self._mode_combo.set_active(MODES.index(self._config.ime.default_mode)
                                    if self._config.ime.default_mode in MODES else 0)
        grid.attach(self._mode_combo, 1, 0, 1, 1)

        self._auto_punct = Gtk.CheckButton(label="自动中英标点切换")
        self._auto_punct.set_active(self._config.ime.auto_punct)
        grid.attach(self._auto_punct, 0, 1, 2, 1)

        self._full_width = Gtk.CheckButton(label="默认全角标点")
        self._full_width.set_active(self._config.ime.full_width_default)
        grid.attach(self._full_width, 0, 2, 2, 1)

        grid.attach(Gtk.Label(label="候选数:", xalign=1), 0, 3, 1, 1)
        self._max_cands = Gtk.SpinButton.new_with_range(1, 9, 1)
        self._max_cands.set_value(self._config.ime.max_candidates)
        grid.attach(self._max_cands, 1, 3, 1, 1)

        return _wrap(grid)

    def _build_shortcuts_tab(self) -> Gtk.Box:
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_border_width(16)
        self._shortcut_entries: dict[str, Gtk.Entry] = {}
        for i, (action, spec) in enumerate(self._config.shortcuts.as_dict().items()):
            grid.attach(Gtk.Label(label=_humanize(action) + ":", xalign=1), 0, i, 1, 1)
            entry = Gtk.Entry()
            entry.set_text(spec)
            entry.set_width_chars(20)
            self._shortcut_entries[action] = entry
            grid.attach(entry, 1, i, 1, 1)
        return _wrap(grid)

    def _build_asr_tab(self) -> Gtk.Box:
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_border_width(16)

        grid.attach(Gtk.Label(label="Provider:", xalign=1), 0, 0, 1, 1)
        self._provider_combo = Gtk.ComboBoxText()
        for p in ("openai", "azure", "google", "custom"):
            self._provider_combo.append_text(p)
        self._provider_combo.set_active(0)
        grid.attach(self._provider_combo, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="API 端点:", xalign=1), 0, 1, 1, 1)
        self._api_endpoint = Gtk.Entry()
        self._api_endpoint.set_text(self._config.asr.api_endpoint)
        grid.attach(self._api_endpoint, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="API Key:", xalign=1), 0, 2, 1, 1)
        self._api_key = Gtk.Entry()
        self._api_key.set_visibility(False)
        self._api_key.set_text(self._config.asr.api_key)
        grid.attach(self._api_key, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label="Model:", xalign=1), 0, 3, 1, 1)
        self._model = Gtk.Entry()
        self._model.set_text(self._config.asr.model)
        grid.attach(self._model, 1, 3, 1, 1)

        grid.attach(Gtk.Label(label="语言:", xalign=1), 0, 4, 1, 1)
        self._lang = Gtk.Entry()
        self._lang.set_text(self._config.asr.language)
        grid.attach(self._lang, 1, 4, 1, 1)

        grid.attach(Gtk.Label(label="静默超时 (秒):", xalign=1), 0, 5, 1, 1)
        self._silence = Gtk.SpinButton.new_with_range(0.5, 30, 0.5)
        self._silence.set_value(self._config.asr.silence_timeout)
        grid.attach(self._silence, 1, 5, 1, 1)

        return _wrap(grid)

    def _build_appearance_tab(self) -> Gtk.Box:
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_border_width(16)

        grid.attach(Gtk.Label(label="主题:", xalign=1), 0, 0, 1, 1)
        self._theme = Gtk.ComboBoxText()
        for t in ("system", "dark", "light"):
            self._theme.append_text(t)
        self._theme.set_active(("system", "dark", "light").index(self._config.ui.theme))
        grid.attach(self._theme, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="悬浮窗位置:", xalign=1), 0, 1, 1, 1)
        self._overlay_pos = Gtk.ComboBoxText()
        for p in ("cursor", "fixed"):
            self._overlay_pos.append_text(p)
        self._overlay_pos.set_active(("cursor", "fixed").index(self._config.ui.overlay_position))
        grid.attach(self._overlay_pos, 1, 1, 1, 1)

        return _wrap(grid)

    def _build_about_tab(self) -> Gtk.Box:
        from tux_im import __version__

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(16)
        box.pack_start(Gtk.Label(label="TUX IM"), False, False, 0)
        box.pack_start(Gtk.Label(label=f"版本 {__version__}"), False, False, 0)
        box.pack_start(Gtk.Label(label="Linux IBus 输入法引擎"), False, False, 0)
        box.pack_start(Gtk.Label(label="支持拼音、五笔、wbpy 混打、ASR 语音"), False, False, 0)
        return box

    # ---- actions ----

    def _on_save(self, _btn) -> None:
        from dataclasses import replace

        self._config.ime = replace(
            self._config.ime,
            default_mode=MODES[self._mode_combo.get_active()],
            auto_punct=self._auto_punct.get_active(),
            full_width_default=self._full_width.get_active(),
            max_candidates=int(self._max_cands.get_value()),
        )
        # Shortcuts.
        for action, entry in self._shortcut_entries.items():
            setattr(self._config.shortcuts, action, entry.get_text().strip())
        # ASR.
        self._config.asr = replace(
            self._config.asr,
            api_endpoint=self._api_endpoint.get_text().strip(),
            api_key=self._api_key.get_text().strip(),
            model=self._model.get_text().strip() or "whisper-1",
            language=self._lang.get_text().strip() or "zh",
            silence_timeout=float(self._silence.get_value()),
        )
        # UI.
        self._config.ui = replace(
            self._config.ui,
            theme=("system", "dark", "light")[self._theme.get_active()],
            overlay_position=("cursor", "fixed")[self._overlay_pos.get_active()],
        )
        self._config.save()
        log.info("Config saved to %s", self._config.path)

    def _on_reset(self, _btn) -> None:
        self._config.__init__()  # type: ignore[misc]
        log.info("Config reset to defaults (not yet saved)")

    def show_all(self) -> None:
        self.win.show_all()


def _wrap(widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.pack_start(widget, True, True, 0)
    return box


def _humanize(action: str) -> str:
    return action.replace("_", " ").capitalize()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = Config.load()
    SettingsWindow(config).show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
