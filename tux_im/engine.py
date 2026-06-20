"""Core IBus engine class."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus  # noqa: E402

from tux_im.input.base import KeyResult
from tux_im.input.latin import LatinMode
from tux_im.input.pinyin import PinyinMode
from tux_im.input.wbpy import WbpyMode
from tux_im.input.wubi import WubiMode

if TYPE_CHECKING:
    from tux_im.config.config import Config
    from tux_im.input.lexicon import Lexicon
    from tux_im.shortcut import ShortcutManager

log = logging.getLogger(__name__)

_config: "Config | None" = None
_lexicon: "Lexicon | None" = None
_shortcuts: "ShortcutManager | None" = None

ENGINES_BY_MODE: dict[str, type] = {
    "pinyin": PinyinMode,
    "wubi": WubiMode,
    "wbpy": WbpyMode,
}


# Property key GNOME Shell's IBus indicator watches for the language badge.
# See js/ui/status/keyboard.js in gnome-shell: a property whose key equals
# 'InputMode' has its symbol/label text used as the indicator text instead
# of the static `language` field from the engine descriptor.
INPUT_MODE_PROP_KEY: str = "InputMode"


class TuxEngine(IBus.Engine):
    """Main IBus engine for TUX IM."""

    __gtype_name__ = "TuxEngine"

    def __init__(
        self,
        config: Config | None = None,
        lexicon: Lexicon | None = None,
        shortcuts: ShortcutManager | None = None,
    ) -> None:
        super().__init__()
        self._chinese_mode: bool = True
        self._page_index: int = 0
        self._chinese_prop_key: str = "tux-im:chinese"
        self._chinese_prop: IBus.Property | None = None
        self._initialized: bool = False

    def _lazy_init(self) -> None:
        if self._initialized:
            return
        if _config is None or _lexicon is None or _shortcuts is None:
            log.warning("_lazy_init: globals not ready yet (config=%s, lexicon=%s, shortcuts=%s)", _config, _lexicon, _shortcuts)
            return
        self._initialized = True
        self._active_mode = self._make_mode(_config.ime.default_mode)

    # ---- Mode management ----

    def _make_mode(self, name: str):
        cls = ENGINES_BY_MODE.get(name, PinyinMode)
        if cls is PinyinMode:
            return PinyinMode(_lexicon.pinyin, _config)  # type: ignore[union-attr]
        if cls is WubiMode:
            return WubiMode(_lexicon.wubi, _config)  # type: ignore[union-attr]
        if cls is WbpyMode:
            mode = WbpyMode(_lexicon.pinyin, _config)  # type: ignore[union-attr]
            mode.attach_wubi(_lexicon.wubi)  # type: ignore[union-attr]
            return mode
        return LatinMode(_config)  # type: ignore[union-attr]

    def set_mode(self, name: str) -> None:
        self._lazy_init()
        log.info("Switching input mode: %s", name)
        self._active_mode = self._make_mode(name)
        self._refresh_preedit()
        self._update_chinese_prop()

    def cycle_mode(self, *_args) -> bool:
        log.debug("cycle_mode handler entered")
        self._lazy_init()
        modes = list(ENGINES_BY_MODE.keys())
        try:
            current = self._active_mode.name
            idx = modes.index(current)
        except (AttributeError, ValueError):
            idx = -1
        next_name = modes[(idx + 1) % len(modes)]
        log.info("cycle_mode: %s -> %s", current, next_name)
        self.set_mode(next_name)
        return True

    def toggle_chinese(self) -> bool:
        log.debug("toggle_chinese handler entered")
        self._lazy_init()
        self._chinese_mode = not self._chinese_mode
        log.info("Chinese mode toggled: %s", self._chinese_mode)
        if not self._chinese_mode:
            self._commit_and_reset()
        self._refresh_preedit()
        self._update_chinese_prop()
        log.debug("toggle_chinese: label=%s", "CN" if self._chinese_mode else "EN")
        return True

    # ---- Shortcut handlers (bound to engine, called with engine arg) ----

    def commit_first(self, *_args) -> bool:
        log.debug("commit_first handler entered")
        self._lazy_init()
        if not self._chinese_mode:
            log.debug("commit_first: not chinese mode, pass-through")
            return False
        if not self._active_mode.buffer:
            log.debug("commit_first: empty buffer, pass-through")
            return False
        # Even if there are no visible candidates (preedit only), space
        # should commit the top latent candidate from the active segment.
        result = self._active_mode.commit()
        log.info("commit_first: committed=%r", result)
        if result:
            self.commit_text(IBus.Text.new_from_string(result))
            # Learn: space commits the top candidate implicitly.
            if self._config.dict.learn_enabled and self._lexicon:
                buf = self._active_mode.buffer
                mode_name = self._active_mode.name
                trie = (self._lexicon.pinyin if mode_name == "pinyin"
                        else self._lexicon.wubi if mode_name in ("wubi", "wbpy")
                        else None)
                if trie is not None:
                    trie.boost(buf, result)
        self._active_mode.reset()
        self._refresh_preedit()
        return True

    def select_candidate(self, index: int, *_args) -> bool:
        log.debug("select_candidate(%d) handler entered", index)
        self._lazy_init()
        if not self._chinese_mode:
            log.debug("select_candidate(%d): not chinese mode, pass-through", index)
            return False
        result = self._active_mode.select(index)
        log.info("select_candidate(%d): commit=%r handled=%s", index, result.commit, result.handled)
        if result.commit is not None:
            self.commit_text(IBus.Text.new_from_string(result.commit))
            # Learn: boost the selected entry so it ranks higher next time.
            if self._config.dict.learn_enabled and self._lexicon:
                buf = self._active_mode.buffer
                if buf:
                    mode_name = self._active_mode.name
                    trie = (self._lexicon.pinyin if mode_name == "pinyin"
                            else self._lexicon.wubi if mode_name in ("wubi", "wbpy")
                            else None)
                    if trie is not None:
                        trie.boost(buf, result.commit)
        if result.clear:
            self._active_mode.reset()
        self._refresh_preedit()
        return result.handled

    def page_candidates(self, direction: int, *_args) -> bool:
        log.debug("page_candidates(%d) handler entered", direction)
        self._lazy_init()
        if not self._chinese_mode:
            log.debug("page_candidates(%d): not chinese mode, pass-through", direction)
            return False
        self._active_mode.page(direction)
        self._refresh_preedit()
        return True

    def delete_left(self, *_args) -> bool:
        log.debug("delete_left handler entered, chinese_mode=%s buffer=%r",
                  self._chinese_mode,
                  self._active_mode.buffer if self._initialized else None)
        self._lazy_init()
        if not self._chinese_mode:
            # English mode: pass BackSpace to the app.
            log.debug("delete_left: english mode, pass-through")
            return False
        if self._active_mode.buffer:
            self._active_mode.buffer = self._active_mode.buffer[:-1]
            self._active_mode.cursor = len(self._active_mode.buffer)
            self._refresh_preedit()
            log.debug("delete_left: buffer=%r", self._active_mode.buffer)
            return True
        # Chinese mode but buffer empty: pass BackSpace to the app.
        log.debug("delete_left: chinese mode but empty buffer, pass-through")
        return False

    def cancel_composition(self, *_args) -> bool:
        log.debug("cancel_composition handler entered")
        self._lazy_init()
        if not self._chinese_mode:
            log.debug("cancel_composition: not chinese mode, pass-through")
            return False
        if self._active_mode.buffer:
            self._active_mode.reset()
            self._refresh_preedit()
            log.debug("cancel_composition: buffer cleared")
            return True
        log.debug("cancel_composition: empty buffer, pass-through")
        return False

    # ---- IBus lifecycle hooks ----

    def do_focus_in(self) -> None:  # type: ignore[override]
        log.debug("focus_in: registering properties")
        self._lazy_init()
        prop_list = self._build_prop_list()
        log.debug("focus_in: properties registered")
        self.register_properties(prop_list)
        log.debug("focus_in: done")

    def do_focus_out(self) -> None:  # type: ignore[override]
        log.debug("focus_out")
        self._commit_and_reset()

    def do_reset(self) -> None:  # type: ignore[override]
        log.debug("reset")
        self._commit_and_reset()

    def do_enable(self) -> None:  # type: ignore[override]
        log.debug("enable: registering shortcut handlers")
        self._lazy_init()
        # Register all shortcut handlers.  Clearing first makes enable
        # idempotent (can be called multiple times without duplication).
        _shortcuts.reset()  # type: ignore[union-attr]
        _shortcuts.register("toggle_en_cn", self.toggle_chinese)  # type: ignore[union-attr]
        _shortcuts.register("commit_first", self.commit_first)  # type: ignore[union-attr]
        _shortcuts.register("delete_left", self.delete_left)  # type: ignore[union-attr]
        _shortcuts.register("cancel", self.cancel_composition)  # type: ignore[union-attr]
        _shortcuts.register("clear_buffer", self.cancel_composition)  # type: ignore[union-attr]
        _shortcuts.register("page_up", lambda *_a: self.page_candidates(-1))  # type: ignore[union-attr]
        _shortcuts.register("page_down", lambda *_a: self.page_candidates(1))  # type: ignore[union-attr]
        _shortcuts.register("cycle_mode", self.cycle_mode)  # type: ignore[union-attr]
        for i in range(9):
            _shortcuts.register(f"candidate_{i + 1}", self._select_n(i))  # type: ignore[union-attr]
        # "0" selects the 10th candidate (Rime/FCITX convention).
        _shortcuts.register("candidate_10", self._select_n(9))  # type: ignore[union-attr]
        log.debug("enable: registered handlers for toggle_en_cn, commit_first, "
                  "delete_left, cancel, clear_buffer, page_up, page_down, "
                  "cycle_mode, candidate_1..10")

    def do_disable(self) -> None:  # type: ignore[override]
        log.debug("disable: committing composition and clearing shortcuts")
        self._commit_and_reset()
        # Remove all shortcut handlers so they don't fire when the engine
        # is inactive.  This also prevents a crash if the engine is destroyed
        # while still active (ibus may call disable before destroy).
        _shortcuts.reset()  # type: ignore[union-attr]
        self._initialized = False

    def do_property_activate(  # type: ignore[override]
        self, prop_name: str, prop_state: int
    ) -> None:
        log.debug("do_property_activate: prop=%s state=%d", prop_name, prop_state)
        # Properties are registered with the "tux-im:<mode>" prefix; strip it
        # so we can match against ENGINES_BY_MODE.
        bare = prop_name.removeprefix("tux-im:")
        if bare in ENGINES_BY_MODE:
            self.set_mode(bare)
            return
        if prop_name == INPUT_MODE_PROP_KEY:
            self.toggle_chinese()
            return

    def _select_n(self, index: int):
        return lambda *_a: self.select_candidate(index)

    def do_process_key_event(  # type: ignore[override]
        self, keyval: int, keycode: int, state: int
    ) -> bool:
        # Filter key-release events up-front. IBus delivers both press and
        # release for every key; only the press should be processed.
        if state & IBus.ModifierType.RELEASE_MASK:
            return False
        log.debug("do_process_key_event: keyval=%d keycode=%d state=0x%x",
                  keyval, keycode, state)
        try:
            return self._handle_key(keyval, state)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:  # pragma: no cover - defensive
            log.exception("Unhandled error processing key %d", keyval)
            self._commit_and_reset()
            # Return True so the key is NOT propagated to the application.
            # An engine that dies silently is far better than one that
            # leaks raw key events into unsuspecting apps.
            return True

    # ---- Key handling ----

    def _handle_key(self, keyval: int, state: int) -> bool:
        self._lazy_init()

        # 1. In Latin mode, let everything pass through.
        if not self._chinese_mode:
            return False

        # 2. Shortcuts first — space (commit_first), Escape (cancel), etc.
        consumed = _shortcuts.handle(self, keyval, state)  # type: ignore[union-attr]
        if consumed:
            self._refresh_preedit()
            return True

        # 3. Hand the key to the active input mode.
        result = self._active_mode.feed_key(keyval, state)
        if result is None:
            return False

        if result.commit is not None:
            self.commit_text(IBus.Text.new_from_string(result.commit))
        if result.clear:
            self._active_mode.reset()
        self._refresh_preedit()
        return result.handled

    # ---- Preedit / candidates ----

    def _refresh_preedit(self) -> None:
        if not self._initialized:
            return
        if not self._chinese_mode:
            self.hide_preedit_text()
            self.hide_auxiliary_text()
            return

        buf = self._active_mode.buffer
        cands = self._active_mode.candidates(_config.ime.max_candidates)  # type: ignore[union-attr]

        if buf or cands:
            # Preedit shows the typed buffer; auxiliary text shows a status
            # badge (mode + buffer + candidate count + top candidate) so the
            # user always has a place to look, even when no IBus panel runs.
            mode_name = self._active_mode.name
            status = f"[{mode_name}] {buf}" if buf else f"[{mode_name}]"
            if cands:
                status = f"{status}  \u2192  {cands[0].text}  ({len(cands)})"
            self.update_preedit_text_with_mode(
                IBus.Text.new_from_string(buf),
                self._active_mode.cursor,
                True,
                IBus.PreeditFocusMode.COMMIT,
            )
            self.update_auxiliary_text(
                IBus.Text.new_from_string(status), False,
            )
            if cands:
                self.update_lookup_table(self._build_lookup(cands), True)
            else:
                self.hide_lookup_table()
        else:
            self.hide_preedit_text()
            self.hide_auxiliary_text()
            self.hide_lookup_table()

    def _build_lookup(self, cands: list) -> IBus.LookupTable:
        table = IBus.LookupTable.new(9, 0, True, False)
        for c in cands:
            text = IBus.Text.new_from_string(c.display)
            table.append_candidate(text)
        return table

    def _build_prop_list(self) -> IBus.PropList:
        prop_list = IBus.PropList.new()
        log.debug("_build_prop_list: creating props for modes %s, chinese_mode=%s", list(ENGINES_BY_MODE.keys()), self._chinese_mode)
        for name in ENGINES_BY_MODE:
            prop = IBus.Property.new(
                f"tux-im:{name}",
                IBus.PropType.NORMAL,
                IBus.Text.new_from_string(name.capitalize()),
                "",
                IBus.Text.new_from_string(""),
                True,
                True,
                IBus.PropState.UNCHECKED,
            )
            prop_list.append(prop)
        label = self._input_mode_label()
        state = IBus.PropState.CHECKED if self._chinese_mode else IBus.PropState.UNCHECKED
        log.debug("_build_prop_list: InputMode prop label=%s state=%s", label, state)
        self._chinese_prop = IBus.Property.new(
            INPUT_MODE_PROP_KEY,
            IBus.PropType.TOGGLE,
            IBus.Text.new_from_string(label),
            "",
            IBus.Text.new_from_string(""),
            True,
            True,
            state,
        )
        # GNOME Shell's indicator shows the symbol text of the InputMode prop
        # in place of the static engine language. See js/ui/status/keyboard.js
        # in gnome-shell: when a registered property has key === "InputMode",
        # the indicator label is taken from its symbol (falling back to label).
        self._chinese_prop.set_symbol(IBus.Text.new_from_string(label))
        prop_list.append(self._chinese_prop)
        log.debug("_build_prop_list: returning prop_list, _chinese_prop=%s", self._chinese_prop)
        return prop_list

    def _update_chinese_prop(self) -> None:
        if not self._initialized or self._chinese_prop is None:
            log.debug("_update_chinese_prop: skipping, not ready")
            return
        label = self._input_mode_label()
        state = IBus.PropState.CHECKED if self._chinese_mode else IBus.PropState.UNCHECKED
        log.debug("_update_chinese_prop: updating, label=%s state=%s", label, state)
        self._chinese_prop.set_state(state)
        self._chinese_prop.set_label(IBus.Text.new_from_string(label))
        self._chinese_prop.set_symbol(IBus.Text.new_from_string(label))
        self.update_property(self._chinese_prop)

    def _input_mode_label(self) -> str:
        """Short label for the InputMode property shown in the IBus indicator.

        GNOME Shell's keyboard.js renders the symbol/label text of the
        InputMode property as the indicator badge. When Chinese mode is on we
        show the active sub-mode abbreviation so the user can tell pinyin /
        wubi / wbpy apart at a glance.
        """
        if not self._chinese_mode:
            return "EN"
        try:
            mode_name = self._active_mode.name
        except AttributeError:
            return "CN"
        return {"pinyin": "拼", "wubi": "五", "wbpy": "混"}.get(mode_name, "CN")

    # ---- Commit / reset ----

    def _commit_and_reset(self) -> None:
        if not self._initialized:
            return
        pending = self._active_mode.commit()  # type: ignore[union-attr]
        if pending:
            self.commit_text(IBus.Text.new_from_string(pending))
        self._active_mode.reset()
        self.hide_preedit_text()
        self.hide_auxiliary_text()

    def quit(self) -> None:
        from gi.repository import IBus as _IBus

        _IBus.quit()
