"""Settings panel for TUX IM (runs as `tux-im-setup`)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from tux_im.config.config import Config

log = logging.getLogger(__name__)

MODES = ["pinyin", "wubi", "wbpy"]
ORIENTATIONS = ["horizontal", "vertical"]
TUX_THEMES = ["system", "TuxDark", "TuxLight", "TuxRetro",
                  "Frost", "Forest", "Sunset", "Solarized",
                  "Catppuccin", "Nord", "Dracula", "RosePine"]


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
        grid = Gtk.Grid(column_spacing=8, row_spacing=10)
        grid.set_border_width(16)

        # --- Candidate orientation ---
        grid.attach(Gtk.Label(label="候选词方向:", xalign=1), 0, 0, 1, 1)
        self._orient_combo = Gtk.ComboBoxText()
        for o in ORIENTATIONS:
            label = {"horizontal": "横向", "vertical": "纵向"}[o]
            self._orient_combo.append_text(label)
        idx = ORIENTATIONS.index(self._config.ui.candidate_orientation) \
            if self._config.ui.candidate_orientation in ORIENTATIONS else 0
        self._orient_combo.set_active(idx)
        grid.attach(self._orient_combo, 1, 0, 1, 1)

        # --- GTK Theme for IBus panel ---
        grid.attach(Gtk.Label(label="候选框主题:", xalign=1), 0, 1, 1, 1)
        self._gtk_theme = Gtk.ComboBoxText()
        for t in TUX_THEMES:
            label = {
                "system":      "跟随系统",
                "TuxDark":    "TuxDark (暗色)",
                "TuxLight":   "TuxLight (亮色)",
                "TuxRetro":   "TuxRetro (复古)",
                "Frost":      "Frost (冰蓝)",
                "Forest":     "Forest (森林)",
                "Sunset":     "Sunset (暖橙)",
                "Solarized":  "Solarized",
                "Catppuccin": "Catppuccin (紫灰)",
                "Nord":       "Nord (北极蓝)",
                "Dracula":    "Dracula (紫红)",
                "RosePine":   "RosePine (玫瑰粉)",
            }[t]
            self._gtk_theme.append_text(label)
        idx = TUX_THEMES.index(self._config.ui.theme) \
            if self._config.ui.theme in TUX_THEMES else 0
        self._gtk_theme.set_active(idx)
        grid.attach(self._gtk_theme, 1, 1, 1, 1)

        # --- Apply theme button ---
        self._theme_status = Gtk.Label(label="")
        self._theme_status.set_halign(Gtk.Align.START)
        grid.attach(self._theme_status, 1, 2, 1, 1)

        apply_btn = Gtk.Button(label="应用主题")
        apply_btn.connect("clicked", self._on_apply_theme)
        grid.attach(apply_btn, 0, 2, 1, 1)

        # --- Info note ---
        note = Gtk.Label(
            label="提示: 主题修改后需要重启 IBus 或重新登录才能生效。\n"
            "候选词方向立即生效，但建议重启 IBus。"
        )
        note.set_halign(Gtk.Align.START)
        note.set_line_wrap(True)
        note.set_max_width_chars(48)
        grid.attach(note, 0, 3, 2, 1)

        return _wrap(grid)

    def _on_apply_theme(self, _btn: object) -> None:
        """Apply the selected GTK theme via gsettings (GNOME) or similar."""
        theme_name = TUX_THEMES[self._gtk_theme.get_active()]
        if theme_name == "system":
            self._theme_status.set_label("已设为跟随系统主题。")
            return

        success = False
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

        # Try GNOME (gsettings)
        if "gnome" in desktop or "unity" in desktop:
            try:
                subprocess.run(
                    ["gsettings", "set", "org.gnome.desktop.interface",
                     "gtk-theme", theme_name],
                    check=True, capture_output=True,
                )
                success = True
                msg = f"已将 GTK 主题设为 {theme_name}。请重启 IBus 或重新登录。"
            except (subprocess.CalledProcessError, FileNotFoundError):
                msg = f"gsettings 失败，请手动设置 GTK 主题为 {theme_name}。"
        else:
            msg = f"请在系统设置中将 GTK 主题改为 {theme_name}。"

        self._theme_status.set_label(msg)

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

    def _on_save(self, _btn: object) -> None:
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
            theme=TUX_THEMES[self._gtk_theme.get_active()],
            candidate_orientation=ORIENTATIONS[self._orient_combo.get_active()],
        )
        self._config.save()
        log.info("Config saved to %s", self._config.path)

    def _on_reset(self, _btn: object) -> None:
        self._config.__init__()  # type: ignore[misc]
        log.info("Config reset to defaults (not yet saved)")

    def show_all(self) -> None:
        self.win.show_all()


def _wrap(widget: Gtk.Widget) -> Gtk.Box:
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
