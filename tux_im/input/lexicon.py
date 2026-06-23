"""Backwards-compatibility shim.

All public names have moved to tux_im.input.lexicon (the subpackage).
This file re-exports them so that existing imports continue to work.
"""

from __future__ import annotations

# Re-export everything from the new subpackage.
from tux_im.input.lexicon import (
    LexEntry,
    Lexicon,
    Trie,
    load_rime_dict,
)

__all__ = ["LexEntry", "Lexicon", "Trie", "load_rime_dict"]
