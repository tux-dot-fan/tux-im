"""Input modes: pinyin, wubi, wbpy, latin."""

from tux_im.input.base import Candidate, InputMode, KeyResult
from tux_im.input.latin import LatinMode
from tux_im.input.pinyin import PinyinMode
from tux_im.input.wbpy import WbpyMode
from tux_im.input.wubi import WubiMode

__all__ = [
    "Candidate",
    "InputMode",
    "KeyResult",
    "LatinMode",
    "PinyinMode",
    "WbpyMode",
    "WubiMode",
]
