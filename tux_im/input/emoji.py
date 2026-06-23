"""Emoji input mode with a built-in emoji trie.

Emoji are triggered by typing a colon followed by a keyword:
  e.g. ":cat" -> 🐱, ":smile" -> 😄, ":+1" -> 👍

The colon prefix is consumed as a mode-switch signal and is not
included in the keyword buffer.
"""

from __future__ import annotations

from typing import Optional

from tux_im.input.base import Candidate, InputMode, KeyResult
from tux_im.input.lexicon import Trie


# ---- Built-in emoji dictionary ----

_EMOJI_DICT: list[tuple[str, str]] = [
    # People & faces
    ("smile", "\U0001F604"),
    ("smiley", "\U0001F603"),
    ("grin", "\U0001F600"),
    ("laugh", "\U0001F602"),
    ("rofl", "\U0001F923"),
    ("blush", "\U0001F60A"),
    ("wink", "\U0001F609"),
    ("kiss", "\U0001F618"),
    ("heart_eyes", "\U0001F60D"),
    ("thinking", "\U0001F914"),
    ("facepalm", "\U0001F926"),
    ("pray", "\U0001F64F"),
    ("wave", "\U0001F44B"),
    ("clap", "\U0001F44F"),
    ("thumbsup", "\U0001F44D"),
    ("thumbsdown", "\U0001F44E"),
    ("ok_hand", "\U0001F44C"),
    ("point_right", "\U0001F449"),
    ("v", "\u270C"),
    ("metal", "\U0001F918"),
    ("fist", "\u270A"),
    ("punch", "\U0001F44A"),
    ("raised_hands", "\U0001F64C"),
    ("couple", "\U0001F46B"),
    ("family", "\U0001F46A"),
    ("kiss_cat", "\U0001F63D"),
    # Animals
    ("cat", "\U0001F431"),
    ("dog", "\U0001F436"),
    ("mouse", "\U0001F42D"),
    ("rabbit", "\U0001F430"),
    ("bear", "\U0001F43B"),
    ("koala", "\U0001F428"),
    ("tiger", "\U0001F42F"),
    ("lion", "\U0001F981"),
    ("pig", "\U0001F437"),
    ("frog", "\U0001F438"),
    ("dragon", "\U0001F409"),
    ("snake", "\U0001F40D"),
    ("turtle", "\U0001F422"),
    ("fish", "\U0001F41F"),
    ("bug", "\U0001F41B"),
    ("ant", "\U0001F41C"),
    ("bee", "\U0001F41D"),
    ("beetle", "\U0001F41E"),
    ("bird", "\U0001F426"),
    ("chicken", "\U0001F414"),
    ("penguin", "\U0001F427"),
    ("elephant", "\U0001F418"),
    ("monkey", "\U0001F435"),
    ("unicorn", "\U0001F984"),
    # Nature
    ("sun", "\u2600"),
    ("cloud", "\u2601"),
    ("rainbow", "\U0001F308"),
    ("snow", "\u2744"),
    ("zap", "\u26A1"),
    ("fire", "\U0001F525"),
    ("water", "\U0001F4A7"),
    ("earth", "\U0001F30D"),
    ("moon", "\U0001F319"),
    ("star", "\u2B50"),
    ("sparkles", "\u2728"),
    ("seedling", "\U0001F331"),
    ("leaf", "\U0001F343"),
    ("tree", "\U0001F333"),
    ("palm_tree", "\U0001F334"),
    ("cactus", "\U0001F335"),
    ("tulip", "\U0001F337"),
    ("rose", "\U0001F339"),
    ("hibiscus", "\U0001F33A"),
    ("sunflower", "\U0001F33B"),
    ("cherry_blossom", "\U0001F338"),
    ("maple_leaf", "\U0001F341"),
    ("mushroom", "\U0001F344"),
    ("shell", "\U0001F41A"),
    ("crab", "\U0001F980"),
    # Food
    ("apple", "\U0001F34E"),
    ("pear", "\U0001F350"),
    ("cherry", "\U0001F352"),
    ("strawberry", "\U0001F353"),
    ("grapes", "\U0001F347"),
    ("watermelon", "\U0001F349"),
    ("tomato", "\U0001F345"),
    ("eggplant", "\U0001F346"),
    ("carrot", "\U0001F955"),
    ("corn", "\U0001F33D"),
    ("hot_pepper", "\U0001F336"),
    ("pizza", "\U0001F355"),
    ("burger", "\U0001F354"),
    ("fries", "\U0001F35F"),
    ("ramen", "\U0001F35C"),
    ("bread", "\U0001F35E"),
    ("cake", "\U0001F382"),
    ("cookie", "\U0001F36A"),
    ("chocolate", "\U0001F36B"),
    ("coffee", "\u2615"),
    ("tea", "\U0001F375"),
    ("beer", "\U0001F37A"),
    ("wine", "\U0001F377"),
    ("cocktail", "\U0001F378"),
    ("sake", "\U0001F376"),
    ("meat", "\U0001F356"),
    ("fish_cake", "\U0001F365"),
    ("rice", "\U0001F35A"),
    ("spoon", "\U0001F358"),
    # Objects
    ("guitar", "\U0001F3B8"),
    ("piano", "\U0001F3B9"),
    ("microphone", "\U0001F3A4"),
    ("headphones", "\U0001F3A7"),
    ("tv", "\U0001F4FA"),
    ("camera", "\U0001F4F7"),
    ("computer", "\U0001F4BB"),
    ("phone", "\U0001F4F1"),
    ("watch", "\U0001F551"),
    ("alarm", "\u23F0"),
    ("lock", "\U0001F512"),
    ("key", "\U0001F511"),
    ("mail", "\U0001F4E7"),
    ("inbox", "\U0001F4E5"),
    ("pencil", "\U0000270F"),
    ("book", "\U0001F4D6"),
    ("pen", "\U0001F58A"),
    ("scissors", "\u2702"),
    ("ruler", "\U0001F4CF"),
    ("light_bulb", "\U0001F4A1"),
    ("battery", "\U0001F50B"),
    ("bulb", "\U0001F4A1"),
    ("flashlight", "\U0001F526"),
    ("wrench", "\U0001F527"),
    ("hammer", "\U0001F528"),
    ("toolbox", "\U0001F9F0"),
    ("key2", "\U0001F5DD"),
    ("bell", "\U0001F514"),
    ("megaphone", "\U0001F4E3"),
    ("loud_sound", "\U0001F50A"),
    ("mute", "\U0001F507"),
    ("speaker", "\U0001F508"),
    ("balloon", "\U0001F388"),
    ("gift", "\U0001F381"),
    ("tada", "\U0001F389"),
    ("confetti", "\U0001F389"),
    ("medal", "\U0001F3C5"),
    ("trophy", "\U0001F3C6"),
    ("money", "\U0001F4B0"),
    ("dollar", "\U0001F4B5"),
    ("yen", "\U0001F4B4"),
    ("euro", "\U0001F4B6"),
    ("pound", "\U0001F4B7"),
    ("credit_card", "\U0001F4B3"),
    ("moneybag", "\U0001F4B0"),
    ("gem", "\U0001F48E"),
    ("crown", "\U0001F451"),
    ("ring", "\U0001F48D"),
    ("diamond", "\U0001F48E"),
    # Symbols
    ("heart", "\U0001F496"),
    ("broken_heart", "\U0001F494"),
    ("yellow_heart", "\U0001F49B"),
    ("green_heart", "\U0001F49A"),
    ("blue_heart", "\U0001F499"),
    ("purple_heart", "\U0001F49C"),
    ("black_heart", "\U0001F372"),
    ("100", "\U0001F4AF"),
    ("+1", "\U0001F44D"),
    ("-1", "\U0001F44E"),
    ("anger", "\U0001F4A2"),
    ("boom", "\U0001F4A5"),
    ("collision", "\U0001F4A5"),
    ("sweat", "\U0001F613"),
    ("droplet", "\U0001F4A7"),
    ("dizzy", "\U0001F4AB"),
    ("speech", "\U0001F4AC"),
    ("zzz", "\U0001F4A4"),
    ("muscle", "\U0001F4AA"),
    ("pray", "\U0001F64F"),
    ("exclamation", "\u2757"),
    ("question", "\u2753"),
    ("exclaim", "\u26A0"),
    ("mood", "\U0001F610"),
    ("neutral", "\U0001F610"),
    ("sob", "\U0001F62D"),
    ("angry", "\U0001F620"),
    ("rage", "\U0001F621"),
    ("cry", "\U0001F622"),
    ("fear", "\U0001F628"),
    ("scream", "\U0001F631"),
    ("tired", "\U0001F4AB"),
    ("muscle", "\U0001F4AA"),
    # Places
    ("house", "\U0001F3E0"),
    ("school", "\U0001F3EB"),
    ("hospital", "\U0001F3E5"),
    ("bank", "\U0001F3E6"),
    ("hotel", "\U0001F3E8"),
    ("love_hotel", "\U0001F3E9"),
    ("convenience_store", "\U0001F3EA"),
    ("store", "\U0001F3EA"),
    ("factory", "\U0001F3ED"),
    ("japan", "\U0001F5FE"),
    ("map", "\U0001F5FA"),
    ("bridge", "\U0001F309"),
    ("sunrise", "\U0001F305"),
    ("sunset", "\U0001F307"),
    ("city", "\U0001F3D0"),
    ("night", "\U0001F303"),
    ("full_moon", "\U0001F319"),
    ("europe", "\U0001F30D"),
    ("asia", "\U0001F30D"),
    ("car", "\U0001F697"),
    ("taxi", "\U0001F695"),
    ("bus", "\U0001F68C"),
    ("train", "\U0001F682"),
    ("bike", "\U0001F6B2"),
    ("rocket", "\U0001F680"),
    ("airplane", "\u2708"),
    ("ship", "\U0001F6A2"),
    ("boat", "\U0001F6A3"),
    ("taxi", "\U0001F695"),
    ("truck", "\U0001F69A"),
    ("ambulance", "\U0001F691"),
    ("fire_engine", "\U0001F692"),
    ("police", "\U0001F693"),
    ("bike", "\U0001F6B2"),
    ("walking", "\U0001F6B6"),
    ("runner", "\U0001F3C3"),
    ("dancer", "\U0001F57A"),
    ("climbing", "\U0001F9D7"),
    # Misc fun
    ("hatching", "\U0001F383"),
    ("moon_clipse", "\U0001F319"),
    ("dvd", "\U0001F4FC"),
    ("gamepad", "\U0001F3AE"),
    ("chess", "\U0001F9F9"),
    ("bowling", "\U0001F3B1"),
    ("pool", "\U0001F3B1"),
    ("game", "\U0001F3AE"),
    ("slot_machine", "\U0001F3B0"),
    ("bow", "\U0001F3F9"),
    ("shooting", "\U0001F3AF"),
    ("star2", "\U0001F31F"),
    ("glowing", "\U0001F31F"),
    ("ribbon", "\U0001F380"),
    ("ball", "\u26BD"),
    ("goal", "\U0001F45F"),
    ("ski", "\U0001F3BF"),
    ("snowboard", "\U0001F3C2"),
    ("surf", "\U0001F3C4"),
    ("fishing", "\U0001F3A3"),
    ("bath", "\U0001F6C1"),
    ("toilet", "\U0001F6BD"),
    ("bed", "\U0001F6CF"),
    ("couch", "\U0001F6CB"),
    ("wc", "\U0001F6BE"),
    ("shower", "\U0001F6BF"),
    ("bathtub", "\U0001F6C1"),
]


# ---- Emoji mode ----

_COLON_KEYVAL = 0x3A  # GDK_COLON


class EmojiMode:
    """Emoji input mode triggered by ':' prefix.

    The user types ':keyword' and gets matching emoji.
    The colon is the mode switch signal; it is stripped from the
    keyword buffer and not shown in the preedit.
    """

    name = "emoji"
    buffer = ""
    cursor = 0

    def __init__(self, config: object) -> None:  # noqa: ARG002
        # Store keyword as code and emoji as word.
        # _trie: code=keyword → word=emoji
        # _emoji_to_keyword: emoji → keyword (reverse lookup)
        self._trie = Trie()
        self._emoji_to_keyword: dict[str, str] = {}
        self._page_offset = 0
        self._emoji_active = False  # set True on first colon, False on commit/escape
        for keyword, emoji in _EMOJI_DICT:
            self._trie.insert(keyword, emoji, freq=0)
            self._emoji_to_keyword[emoji] = keyword

    def feed_key(self, keyval: int, state: int) -> Optional[KeyResult]:  # noqa: ARG002
        """Handle a key press.

        The colon ':' (keyval 0x3A) enters emoji mode.
        After that, alphanumeric keys build the keyword buffer.
        Enter commits the selected emoji; Escape cancels.
        """
        if keyval == _COLON_KEYVAL:
            if not self._emoji_active:
                self._emoji_active = True
                self.buffer = ""
                return KeyResult(handled=True)
            # Second colon: insert literal colon and exit emoji mode.
            self._emoji_active = False
            self.buffer = ""
            return KeyResult(handled=True, commit=":")
        if not self._emoji_active:
            # Not in emoji mode.
            return None
        # Accept a-z, 0-9, underscore for keyword.
        from gi.repository import Gdk
        name = Gdk.keyval_name(keyval)
        if name is None:
            return KeyResult(handled=True)
        lower = name.lower()
        if len(lower) == 1 and (lower.isalnum() or lower == "_"):
            self.buffer += lower
            return KeyResult(handled=True)
        # Any other key: exit emoji mode silently, let engine handle the key.
        self._emoji_active = False
        self.buffer = ""
        return KeyResult(handled=False)

    def reset(self) -> None:
        self.buffer = ""
        self._page_offset = 0
        self._emoji_active = False

    def commit(self) -> Optional[str]:
        """No implicit commit in emoji mode."""
        return None

    def candidates(self, limit: int = 9) -> list[Candidate]:
        if not self.buffer:
            return []
        entries = self._trie.lookup(self.buffer)
        # _trie: code=keyword → word=emoji
        # We need display=keyword, text=emoji
        cands = []
        seen_emoji: set[str] = set()
        seen_keyword: set[str] = set()
        for e in entries:
            if e.word in seen_emoji:
                continue
            seen_emoji.add(e.word)
            keyword = self._emoji_to_keyword.get(e.word, "")
            if not keyword or keyword in seen_keyword:
                continue
            seen_keyword.add(keyword)
            cands.append(Candidate(text=e.word, display=keyword, comment=""))
            if len(cands) >= limit:
                break
        return cands

    def select(self, index: int) -> KeyResult:
        if not self.buffer:
            return KeyResult(handled=False)
        entries = self._trie.lookup(self.buffer)
        seen: set[str] = set()
        candidates: list[str] = []
        for e in entries:
            if e.word in seen:
                continue
            seen.add(e.word)
            # e.word is the emoji char (e.g. "🐱") -- use it directly
            candidates.append(e.word)
        if not (0 <= index < len(candidates)):
            return KeyResult(handled=False)
        emoji = candidates[index]
        self.reset()
        # Return the emoji character as commit text.
        return KeyResult(handled=True, commit=emoji, clear=True)

    def page(self, direction: int) -> KeyResult:
        self._page_offset = max(0, self._page_offset + direction * 9)
        return KeyResult(handled=True)

    def full_sentence(self) -> None:
        """No sentence-level decoding."""
        return None
