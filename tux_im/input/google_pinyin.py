"""Python ctypes binding for libgooglepinyin.

libgooglepinyin: https://github.com/qgears/libgooglepinyin
Dictionary (dict_pinyin.dat) pre-built from rawdict_utf16_65105_freq.txt.

Usage:
    dec = GooglePinyinDecoder()
    dec.open("/path/to/dict_pinyin.dat", "/path/to/user_dict.dat")
    num = dec.search("nihao")       # 搜索整串拼音
    for i in range(num):
        print(dec.get_candidate(i))  # 获取候选
    dec.choose(0)                   # 选第一个候选（锁定首词，对剩余音节重解码）
    dec.reset()                     # 重置
    dec.close()
"""

from __future__ import annotations

import ctypes
import os
from collections.abc import Iterator
from ctypes import POINTER, c_bool, c_char, c_char_p, c_size_t, c_uint16
from pathlib import Path

# ── ctypes type aliases ────────────────────────────────────────────────────────

char16 = c_uint16  # uint16_t = UTF-16 code unit

_char16_p = POINTER(char16)
_const_char16_p = POINTER(c_uint16)  # const uint16_t*


# ── libgooglepinyin C API (extern "C", no name-mangling) ───────────────────────
#
# bool     im_open_decoder(const char *fn_sys_dict, const char *fn_usr_dict)
# void     im_close_decoder()
# size_t   im_search(const char* sps_buf, size_t sps_len)
# size_t   im_add_letter(char ch)
# size_t   im_choose(size_t cand_id)
# size_t   im_cancel_last_choice()
# void     im_reset_search()
# size_t   im_get_fixed_len()
# bool     im_cancel_input()
# void     im_set_max_lens(size_t max_sps_len, size_t max_hzs_len)
# const char*  im_get_sps_str(size_t *decoded_len)
# char16* im_get_candidate(size_t cand_id, char16* cand_str, size_t max_len)
# size_t   im_get_spl_start_pos(const uint16 *&spl_start)
# void     im_flush_cache()

_lib = None  # cached handle


def _load_lib() -> ctypes.CDLL:
    global _lib
    if _lib is not None:
        return _lib

    # Try standard library paths
    for path in (
        "/usr/lib/x86_64-linux-gnu/libgooglepinyin.so",
        "/usr/local/lib/libgooglepinyin.so",
        "libgooglepinyin.so",
    ):
        if os.path.exists(path):
            _lib = ctypes.CDLL(path)
            break
    else:
        raise FileNotFoundError(
            "libgooglepinyin.so not found. "
            "Install with: sudo apt install libgooglepinyin0-dev"
        )

    # ── function signatures ──────────────────────────────────────────────────

    def _sig(restype, *argtypes) -> callable:
        def decorator(func: callable) -> callable:
            func.restype = restype
            func.argtypes = list(argtypes)
            return func

        return decorator

    _sig(c_bool, c_char_p, c_char_p)(_lib.im_open_decoder)
    _sig(None)(_lib.im_close_decoder)
    _sig(c_size_t, c_char_p, c_size_t)(_lib.im_search)
    _sig(c_size_t, c_char)(_lib.im_add_letter)
    _sig(c_size_t, c_size_t)(_lib.im_choose)
    _sig(c_size_t)(_lib.im_cancel_last_choice)
    _sig(None)(_lib.im_reset_search)
    _sig(c_size_t)(_lib.im_get_fixed_len)
    _sig(c_bool)(_lib.im_cancel_input)
    _sig(None, c_size_t, c_size_t)(_lib.im_set_max_lens)
    _sig(c_char_p, POINTER(c_size_t))(_lib.im_get_sps_str)
    # im_get_candidate: char16* (restype) + (c_size_t, _char16_p, c_size_t) (argtypes)
    _lib.im_get_candidate.restype = _char16_p
    _lib.im_get_candidate.argtypes = [c_size_t, _char16_p, c_size_t]
    _sig(c_size_t, POINTER(_const_char16_p))(_lib.im_get_spl_start_pos)
    _sig(None)(_lib.im_flush_cache)

    return _lib


# ── Public API ────────────────────────────────────────────────────────────────


class Candidate:
    """A decoded Chinese candidate with its pinyin segmentation info."""

    __slots__ = ("pinyin_seg", "text")

    def __init__(self, text: str, pinyin_seg: list[str]):
        self.text = text          # e.g. "你好"
        self.pinyin_seg = pinyin_seg  # e.g. ["ni", "hao"]

    def __repr__(self) -> str:
        return f"Candidate({self.text!r}, {self.pinyin_seg!r})"

    def __str__(self) -> str:
        return self.text


class GooglePinyinDecoder:
    """Python wrapper around libgooglepinyin.

    Provides full-sentence pinyin decoding with word-level locking,
    exactly like Google Pinyin / Sogou Pinyin.
    """

    def __init__(
        self,
        sys_dict: str | Path | None = None,
        user_dict: str | Path | None = None,
    ) -> None:
        """
        Args:
            sys_dict:  Path to system dictionary (dict_pinyin.dat).
                       If None, uses the system-installed dict.
            user_dict: Path to user dictionary. Created on first open.
        """
        if sys_dict is None:
            sys_dict = "/usr/lib/x86_64-linux-gnu/googlepinyin/data/dict_pinyin.dat"
        self.sys_dict = str(sys_dict)
        self.user_dict = str(user_dict) if user_dict else "/tmp/google_pinyin_user.dat"
        self._lib = _load_lib()
        self._open: bool = False

    # ── Decoder lifecycle ────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the decoder. Call once before use."""
        ok = self._lib.im_open_decoder(
            self.sys_dict.encode(), self.user_dict.encode()
        )
        if not ok:
            raise RuntimeError(
                f"im_open_decoder failed for {self.sys_dict!r}. "
                "Is the dict file valid?"
            )
        # Reasonable limits for IBus input: 30 pinyin letters, 50 Chinese chars
        self._lib.im_set_max_lens(30, 50)
        self._open = True

    def close(self) -> None:
        """Flush and close the decoder."""
        if self._open:
            self._lib.im_flush_cache()
            self._lib.im_close_decoder()
            self._open = False

    def __enter__(self) -> GooglePinyinDecoder:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ── Core decoding ───────────────────────────────────────────────────────

    def search(self, pinyin: str) -> int:
        """Search a full pinyin string.

        Args:
            pinyin: Raw pinyin letters, e.g. "wozhongguo" or "nihao"

        Returns:
            Number of candidates available.
        """
        b = pinyin.encode("ascii")
        self._lib.im_reset_search()
        return self._lib.im_search(b, len(b))

    def add_letter(self, ch: str) -> int:
        """Add one pinyin letter incrementally.

        Args:
            ch: Single ASCII letter/digit.

        Returns:
            Number of candidates after the add.
        """
        return self._lib.im_add_letter(ch.encode("ascii"))

    def reset(self) -> None:
        """Reset search state (equivalent to pressing Escape)."""
        self._lib.im_reset_search()
        self._lib.im_cancel_input()

    def cancel_last(self) -> int:
        """Undo the last choose. Returns new candidate count."""
        return self._lib.im_cancel_last_choice()

    # ── Candidate access ─────────────────────────────────────────────────────

    def _utf16_buf(self, size: int = 256) -> tuple[_char16_p, list[char16]]:
        """Allocate a mutable UTF-16LE buffer for im_get_candidate."""
        arr = (char16 * size)(*([0] * size))
        return ctypes.cast(arr, _char16_p), arr

    def _utf16_to_str(self, buf: list[char16]) -> str:
        """Decode a null-terminated UTF-16LE buffer to Python str."""
        chars = []
        for c in buf:
            if c == 0:
                break
            # Re-encode as UTF-16LE, then decode as UTF-8
            if c < 0xD800:
                chars.append(chr(c))
            elif c < 0xE000:  # surrogate — shouldn't appear in valid text
                continue
            else:
                chars.append(chr(c))
        return "".join(chars)

    def get_candidate(self, cand_id: int) -> Candidate | None:
        """Get candidate string by numeric id (0-based).

        Returns None if cand_id is out of range.
        """
        buf_p, buf = self._utf16_buf()
        ret = self._lib.im_get_candidate(cand_id, buf_p, len(buf) - 1)
        if not ret:
            return None

        # Build pinyin segmentation from spl_start
        decoded_len = c_size_t()
        sps = self._lib.im_get_sps_str(ctypes.byref(decoded_len))
        if not sps:
            return None

        sps_str = sps[: decoded_len.value].decode("ascii")

        # Get spelling boundaries
        spl_start_ptr: _const_char16_p = _const_char16_p()
        n_splits = self._lib.im_get_spl_start_pos(ctypes.byref(spl_start_ptr))
        if n_splits == 0:
            return None

        # Read spl_start array
        spl_start = [spl_start_ptr[i] for i in range(n_splits + 1)]

        # Extract pinyin segments
        pinyin_seg: list[str] = []
        for i in range(n_splits):
            pinyin_seg.append(sps_str[spl_start[i] : spl_start[i + 1]])

        # Get fixed_len to know how many segments are already locked
        self._lib.im_get_fixed_len()
        # The candidate text is the full decoded Chinese string
        text = self._utf16_to_str(buf)

        return Candidate(text=text, pinyin_seg=pinyin_seg)

    def candidates(self, limit: int = 9) -> Iterator[Candidate]:
        """Iterate over all candidates (up to ``limit``)."""
        self._lib.im_get_sps_str(ctypes.byref(c_size_t()))
        # We don't know total count; im_search/im_choose returns it
        # We'll use the most recent count cached by the wrapper
        # For safety, cap at limit
        for i in range(limit):
            c = self.get_candidate(i)
            if c is None:
                break
            yield c

    # ── Word locking ─────────────────────────────────────────────────────────

    def choose(self, cand_id: int) -> int:
        """Select candidate ``cand_id``, lock its first word, re-decode rest.

        This is the key method for incremental sentence construction:
        1. User picks a candidate from the list.
        2. The first word of that candidate is "locked" (fixed).
        3. The engine re-decodes remaining unfixed pinyin and returns
           a new candidate list.

        Args:
            cand_id: Index of the candidate to choose (0-based).

        Returns:
            Number of new candidates for the remaining (unfixed) portion.
        """
        return self._lib.im_choose(cand_id)

    def fixed_len(self) -> int:
        """Return number of Chinese characters already locked by choose()."""
        return self._lib.im_get_fixed_len()
