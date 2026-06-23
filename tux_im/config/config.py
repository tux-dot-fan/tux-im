"""Configuration loader and schema for TUX IM."""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tux-im"
CONFIG_PATH = CONFIG_DIR / "config.toml"


@dataclass
class IMESection:
    default_mode: str = "pinyin"
    auto_punct: bool = True
    full_width_default: bool = False
    show_pinyin_in_preedit: bool = True
    max_candidates: int = 9


@dataclass
class ShortcutSection:
    toggle_en_cn: str = "Caps_Lock"
    start_asr: str = "<Ctrl>grave"
    commit_first: str = "space"
    candidate_1: str = "1"
    candidate_2: str = "2"
    candidate_3: str = "3"
    candidate_4: str = "4"
    candidate_5: str = "5"
    candidate_6: str = "6"
    candidate_7: str = "7"
    candidate_8: str = "8"
    candidate_9: str = "9"
    page_up: str = "bracketleft"
    page_down: str = "bracketright"
    cycle_mode: str = "<Ctrl><Shift>m"
    toggle_full_width: str = "<Shift>space"
    open_settings: str = "<Ctrl>comma"
    cancel: str = "Escape"
    delete_left: str = "BackSpace"
    clear_buffer: str = "Escape"

    def as_dict(self) -> dict[str, str]:
        return {
            "toggle_en_cn": self.toggle_en_cn,
            "start_asr": self.start_asr,
            "commit_first": self.commit_first,
            "candidate_1": self.candidate_1,
            "candidate_2": self.candidate_2,
            "candidate_3": self.candidate_3,
            "candidate_4": self.candidate_4,
            "candidate_5": self.candidate_5,
            "candidate_6": self.candidate_6,
            "candidate_7": self.candidate_7,
            "candidate_8": self.candidate_8,
            "candidate_9": self.candidate_9,
            "page_up": self.page_up,
            "page_down": self.page_down,
            "cycle_mode": self.cycle_mode,
            "toggle_full_width": self.toggle_full_width,
            "open_settings": self.open_settings,
            "cancel": self.cancel,
            "delete_left": self.delete_left,
            "clear_buffer": self.clear_buffer,
        }


@dataclass
class ASRSection:
    provider: str = "openai"
    api_endpoint: str = "https://api.openai.com/v1/audio/transcriptions"
    api_key: str = ""
    language: str = "zh"
    timeout: int = 30
    sample_rate: int = 16000
    channels: int = 1
    silence_timeout: float = 2.0
    max_duration: int = 60
    model: str = "whisper-1"


@dataclass
class UISection:
    theme: str = "system"
    overlay_position: str = "cursor"
    overlay_offset_x: int = 0
    overlay_offset_y: int = 24
    font_size: int = 14


@dataclass
class DictSection:
    search_paths: list[str] = field(default_factory=lambda: [
        "/usr/share/rime-data",
        str(CONFIG_DIR / "dicts"),
        "./data",
    ])
    user_words_path: str = str(CONFIG_DIR / "user_words.txt")
    learn_enabled: bool = True


@dataclass
class Config:
    path: Path = CONFIG_PATH
    ime: IMESection = field(default_factory=IMESection)
    shortcuts: ShortcutSection = field(default_factory=ShortcutSection)
    asr: ASRSection = field(default_factory=ASRSection)
    ui: UISection = field(default_factory=UISection)
    dictionary: DictSection = field(default_factory=DictSection)

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        path = path or CONFIG_PATH
        cfg = cls(path=path)
        if not path.exists():
            log.info("No config at %s, using defaults", path)
            return cfg
        try:
            with path.open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            log.warning("Failed to load %s: %s -- using defaults", path, exc)
            return cfg
        cfg._apply(data)
        log.info("Loaded config from %s", path)
        return cfg

    def _apply(self, data: dict[str, Any]) -> None:
        if "ime" in data:
            self.ime = _merge(self.ime, data["ime"])
        if "asr" in data:
            self.asr = _merge(self.asr, data["asr"])
        if "ui" in data:
            self.ui = _merge(self.ui, data["ui"])
        if "dictionary" in data:
            self.dictionary = _merge(self.dictionary, data["dictionary"])
        if "ime" in data and "shortcuts" in data["ime"]:
            self.shortcuts = _merge(self.shortcuts, data["ime"]["shortcuts"])

    def save(self) -> None:
        import tomli_w

        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "ime": {
                "default_mode": self.ime.default_mode,
                "auto_punct": self.ime.auto_punct,
                "full_width_default": self.ime.full_width_default,
                "show_pinyin_in_preedit": self.ime.show_pinyin_in_preedit,
                "max_candidates": self.ime.max_candidates,
                "shortcuts": self.shortcuts.as_dict(),
            },
            "asr": {
                "provider": self.asr.provider,
                "api_endpoint": self.asr.api_endpoint,
                "api_key": self.asr.api_key,
                "language": self.asr.language,
                "timeout": self.asr.timeout,
                "sample_rate": self.asr.sample_rate,
                "channels": self.asr.channels,
                "silence_timeout": self.asr.silence_timeout,
                "max_duration": self.asr.max_duration,
                "options": {"model": self.asr.model},
            },
            "ui": {
                "theme": self.ui.theme,
                "overlay_position": self.ui.overlay_position,
                "overlay_offset_x": self.ui.overlay_offset_x,
                "overlay_offset_y": self.ui.overlay_offset_y,
                "font_size": self.ui.font_size,
            },
            "dictionary": {
                "search_paths": self.dictionary.search_paths,
                "user_words_path": self.dictionary.user_words_path,
                "learn_enabled": self.dictionary.learn_enabled,
            },
        }
        with self.path.open("wb") as fh:
            tomli_w.dump(data, fh)
        try:
            self.path.chmod(0o600)
        except OSError:  # pragma: no cover
            pass


def _merge(dataclass_obj: Any, data: dict[str, Any]) -> Any:
    """Return a copy of dataclass_obj with fields overridden by data.

    Unknown fields are silently dropped (backwards compatibility when new
    config keys are added).  Type mismatches are also dropped and logged
    so a typo like ``max_candidates = "9"`` (string instead of int) does
    not corrupt the dataclass.
    """
    from dataclasses import replace
    from typing import get_args, get_origin, get_type_hints

    if not isinstance(data, dict):
        return dataclass_obj
    # Resolve annotations to real types.  This module uses
    # `from __future__ import annotations` (PEP 563), so plain
    # `__dataclass_fields__[k].type` is a *string* like "list[str]".
    # get_type_hints() evaluates those strings back into real types.
    try:
        resolved = get_type_hints(type(dataclass_obj))
    except Exception:  # pragma: no cover - defensive
        resolved = {}
    valid: dict[str, Any] = {}
    for k, v in data.items():
        expected_type = resolved.get(k)
        if expected_type is None:
            # Field unknown to get_type_hints (e.g. not in resolved) but
            # still present on the dataclass — accept it without a type
            # check rather than drop on the floor.  This is the
            # backwards-compat path for forward references that
            # get_type_hints could not resolve.
            if not hasattr(dataclass_obj, k):
                log.debug("_merge: unknown field %r, ignoring", k)
                continue
            valid[k] = v
            continue
        origin = get_origin(expected_type)
        if origin is not None:
            # Optional[T] / Union[T, ...] / list[T] / dict[K, V] etc.
            # Strategy: isinstance supports a tuple of types, but it does
            # NOT understand ``list[str]`` — it only checks the *outer*
            # type.  So we must build a check for the origin type itself
            # and validate the inner args recursively.
            args = get_args(expected_type)
            if v is None:
                # None is only valid if NoneType is in args (Optional).
                if type(None) in args:
                    valid[k] = v
                    continue
                log.warning("_merge: field %r expected %r, got None -- ignoring",
                            k, expected_type)
                continue
            if not isinstance(v, origin):
                log.warning("_merge: field %r expected %r, got %r (%s) -- ignoring",
                            k, expected_type, v, type(v).__name__)
                continue
            # For containers, do a shallow inner-type check too.
            if origin in (list, tuple, set, frozenset):
                if args:
                    inner = args[0]
                    if not all(isinstance(x, inner) for x in v):
                        log.warning(
                            "_merge: field %r expected elements of type %r -- ignoring",
                            k, inner,
                        )
                        continue
            elif origin is dict and len(args) == 2:
                k_t, v_t = args
                if not all(isinstance(x, k_t) and isinstance(y, v_t)
                           for x, y in v.items()):
                    log.warning(
                        "_merge: field %r expected dict[%r, %r] -- ignoring",
                        k, k_t, v_t,
                    )
                    continue
            valid[k] = v
            continue
        # Plain type (str, int, bool, float, ...).
        if isinstance(v, expected_type):
            valid[k] = v
            continue
        log.warning("_merge: field %r expected %r, got %r (%s) -- ignoring",
                    k, expected_type, v, type(v).__name__)
    return replace(dataclass_obj, **valid)
