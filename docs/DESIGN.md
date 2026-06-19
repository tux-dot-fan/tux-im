# TUX IM — Design Document

## Overview

TUX IM is an IBus input method engine for Linux that provides:
- **Pinyin** — Standard Chinese phonetic input
- **Wubi 86** — Wangma five-stroke input
- **Wbpy** — Automatic mixed Wubi + Pinyin input
- **ASR** — Voice input via cloud API (with on-screen overlay)

Written primarily in Python using `ibus-python` bindings for rapid development and easy maintenance.

## Goals

- Native integration with IBus framework (works with GNOME, KDE, Sway, etc.)
- Use existing RIME dicts when available; fall back to bundled data
- Minimal dependencies; avoid FFI and external runtime requirements
- Professional UX with consistent shortcuts and config
- Hot-reloadable configuration

## Non-Goals

- Local ASR (we use cloud API)
- iOS/Android support
- Other IM frameworks (fcitx5, etc.) — IBus only

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  IBus Daemon (ibus-daemon)                                  │
│    │                                                        │
│    │  (DBus, IME activation)                                │
│    ▼                                                        │
│  TUX Engine Process (ibus-engine-tux-im)                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  IBusEngine (engine.py)                              │   │
│  │    ├─ InputContext: preedit + candidate window       │   │
│  │    ├─ KeyEventRouter: dispatch to active input mode  │   │
│  │    └─ ShortcutManager: global hotkeys                │   │
│  │                                                       │   │
│  │  ┌─────────────────────────────────────────────────┐ │   │
│  │  │  Input Modes (input/)                            │ │   │
│  │  │    ├─ PinyinMode     (input/pinyin.py)           │ │   │
│  │  │    ├─ WubiMode       (input/wubi.py)             │ │   │
│  │  │    ├─ WbpyMode       (input/wbpy.py)             │ │   │
│  │  │    └─ LatinMode      (input/latin.py)            │ │   │
│  │  └─────────────────────────────────────────────────┘ │   │
│  │                                                       │   │
│  │  ┌─────────────────────────────────────────────────┐ │   │
│  │  │  Lexicon / Tries (input/lexicon.py)             │ │   │
│  │  │    ├─ PinyinTrie   ← pinyin dict                │ │   │
│  │  │    └─ WubiTrie     ← wubi 86 dict                │ │   │
│  │  └─────────────────────────────────────────────────┘ │   │
│  │                                                       │   │
│  │  ┌─────────────────────────────────────────────────┐ │   │
│  │  │  ASR Subsystem (asr/)                            │ │   │
│  │  │    ├─ ASRClient        (httpx streaming)         │ │   │
│  │  │    ├─ AudioCapture     (PyAudio / PortAudio)     │ │   │
│  │  │    └─ OverlayWindow    (GTK no-focus popup)      │ │   │
│  │  └─────────────────────────────────────────────────┘ │   │
│  │                                                       │   │
│  │  ┌─────────────────────────────────────────────────┐ │   │
│  │  │  Config (config/)                                │ │   │
│  │  │    ├─ config.toml  (user prefs)                  │ │   │
│  │  │    ├─ shortcuts    (gsettings)                   │ │   │
│  │  │    └─ FileMonitor  (hot-reload)                  │ │   │
│  │  └─────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

         ┌────────────────────────────────────┐
         │  tux-im-setup (separate process)   │
         │    Settings panel (GTK)            │
         │    Writes config files             │
         └────────────────────────────────────┘
```

## Module Breakdown

### `tux_im/engine.py`
The `IBusEngine` subclass. Owns:
- Preedit string (the typed-but-not-committed text)
- Candidate list (shown in candidate window)
- Connection to active input mode

Hooks called by IBus: `process_key_event`, `focus_in/out`, `reset`, `enable/disable`.

### `tux_im/input/`
Each mode implements the `InputMode` interface:

```python
class InputMode(Protocol):
    name: str
    
    def feed_key(self, keyval, state) -> KeyResult: ...
    def commit(self) -> str | None: ...
    def reset(self) -> None: ...
    def candidates(self) -> list[Candidate]: ...
    def lookup_more(self, n: int) -> list[Candidate]: ...  # page down
    def lookup_less(self, n: int) -> list[Candidate]: ...  # page up
```

- **PinyinMode** — buffers pinyin (a-z + tone numbers 1-5), queries PinyinTrie
- **WubiMode** — buffers wubi code (1-4 letters), queries WubiTrie
- **WbpyMode** — routes each keystroke to both PinyinTrie and WubiTrie, merges candidates with Wubi prioritized for short (≤4) codes that are valid wubi prefixes
- **LatinMode** — passes through, just commits ASCII

### `tux_im/input/lexicon.py`
Prefix-tree (trie) structures for fast prefix lookup:

```python
class PinyinTrie:
    # pinyin (e.g., "ni3") -> list of (chinese_word, freq)
    ...

class WubiTrie:
    # wubi code (e.g., "kld") -> list of (chinese_word, freq)
    ...
```

Loads from RIME dict format or bundled data files.

### `tux_im/asr/`
- **ASRClient** — wraps `httpx` for the chosen API. Pluggable provider interface.
- **AudioCapture** — records from default mic via PyAudio
- **OverlayWindow** — GTK popup window, no focus, always-on-top, near cursor

States: `IDLE → RECORDING → PROCESSING → RESULT → IDLE`

### `tux_im/ui/`
GTK widgets and windows:
- `OverlayWindow` — ASR floating window
- `CandidatePanel` — IBus auxiliary text (standard IBus UI)

### `tux_im/config/`
- `Config` class — loads/saves TOML
- `ShortcutManager` — wraps `gsettings` for hotkeys
- `FileMonitor` — watches `~/.config/tux-im/config.toml` for changes

## Data Flow

### Typing a Chinese character (Pinyin mode)

```
User presses 'n'
  → IBus daemon → TUX engine
  → engine.process_key_event('n')
  → active_mode.feed_key('n')
  → PinyinMode buffers "n"
  → PinyinTrie.prefix("n") → candidates
  → engine.update_preedit("n", candidates)
  → IBus shows preedit + candidate window

User presses 'i', '3'
  → PinyinMode buffers "ni3"
  → PinyinTrie.prefix("ni3") → ["你", "泥", "尼", ...]
  → engine.update_preedit("ni3", candidates)

User presses Space
  → engine commits first candidate "你"
  → active_mode.reset()
```

### ASR flow

```
User presses Ctrl+`
  → ShortcutManager fires
  → ASRHandler.start()
  → AudioCapture.start_recording()
  → OverlayWindow.show_at_cursor()
  → state = RECORDING

[streaming interim results from API]
  → ASRClient receives partial text
  → OverlayWindow.update_interim(text)

User presses Ctrl+` again (or silence timeout)
  → AudioCapture.stop()
  → ASRClient.finalize()
  → state = PROCESSING
  → OverlayWindow.show_result(text, alternatives)

User presses Enter
  → engine.commit(text)
  → OverlayWindow.hide()
  → state = IDLE
```

## Interaction Design (UX)

### Shortcuts

| Action | Shortcut |
|---|---|
| Toggle EN/CN | `Capslock` |
| Start/stop ASR | ``Ctrl+` `` |
| Commit first candidate | `Space` |
| Commit candidate N | `1`–`9` |
| Page down candidates | `]` |
| Page up candidates | `[` |
| Cycle input mode | `Ctrl+Shift+M` (optional) |
| Full-width toggle | `Shift+Space` |
| Open settings | `Ctrl+,` |

### Punctuation auto-mapping (when CN mode active)

- `.` → `。`
- `,` → `，`
- `?` → `？`
- `!` → `！`
- `:` → `：`
- `;` → `；`
- `"` → `""` (paired)
- `'` → `''` (paired)
- `(` → `（）` (paired)
- `[` → `【】` (paired)
- `<` → `《》` (paired)

### ASR Overlay

States with visual feedback:
- `IDLE` — window hidden
- `RECORDING` — pulsing mic icon, audio level bars, elapsed time
- `PROCESSING` — spinner
- `RESULT` — editable text, ASR alternatives, action buttons

Interactions in overlay state:
- `Enter`/`Space` — commit
- `Tab` — cycle alternatives
- `Esc` — cancel
- Click outside — commit and close
- `Backspace` — edit inline

## Configuration

File: `~/.config/tux-im/config.toml` (TOML, hot-reloaded)

```toml
[ime]
default_mode = "pinyin"
auto_punct = true
full_width_default = false

[ime.shortcuts]
toggle_en_cn = "Caps_Lock"
start_asr = "<Ctrl>grave"
commit_first = "space"
page_up = "bracketleft"
page_down = "bracketright"
cycle_mode = "<Ctrl><Shift>m"

[asr]
provider = "openai"
api_endpoint = "https://api.openai.com/v1/audio/transcriptions"
api_key = ""
language = "zh"
timeout = 30

[ui]
theme = "system"
overlay_position = "cursor"
```

## File Layout

```
tux-im/
├── README.md
├── LICENSE
├── setup.py
├── pyproject.toml
├── data/
│   ├── pinyin.dict.yaml
│   └── wubi86.dict.yaml
├── docs/
│   ├── DESIGN.md
│   ├── ARCHITECTURE.md
│   ├── CONFIGURATION.md
│   └── DEVELOPMENT.md
├── tux_im/
│   ├── __init__.py
│   ├── engine.py            # IBusEngine
│   ├── main.py              # Entry point
│   ├── shortcut.py          # ShortcutManager
│   ├── input/
│   │   ├── __init__.py
│   │   ├── base.py          # InputMode protocol
│   │   ├── pinyin.py
│   │   ├── wubi.py
│   │   ├── wbpy.py
│   │   ├── latin.py
│   │   └── lexicon.py       # Trie structures
│   ├── asr/
│   │   ├── __init__.py
│   │   ├── client.py        # ASR API client
│   │   ├── capture.py       # Audio capture
│   │   └── overlay.py       # Overlay window
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── candidate.py
│   │   └── settings.py      # Settings panel
│   ├── config/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── monitor.py
│   └── dict_loader.py
├── setup/
│   ├── ibus-engine-tux-im.in
│   ├── tux-im-setup.desktop
│   └── 50-ibus-tux-im.rules
└── tests/
    ├── test_pinyin.py
    ├── test_wubi.py
    ├── test_wbpy.py
    └── test_lexicon.py
```

## Dependencies

**Runtime:**
- `ibus-1.0` (system package)
- `python3-gi` (system package)
- `python3-ibus-1.0` (system package, or `ibus` from PyPI)
- `PyGObject` (introspection)
- `tomllib` (Python 3.11+, or `tomli`)
- `httpx` (ASR API)
- `pyaudio` or `sounddevice` (mic capture)

**Build:**
- `setuptools`, `wheel`
- `meson` and `ninja` (for installing IBus component XML)

**Dev:**
- `pytest`, `pytest-asyncio`
- `ruff`, `mypy`

## Testing Strategy

- **Unit tests** for each input mode (feed_key, commit, candidates)
- **Trie tests** for lexicon load + lookup
- **Integration tests** for engine (mock IBus)
- **Manual test plan** for ASR (real mic + API)

## Future Extensions

- Plugin system for custom modes
- User dictionary (learn new words)
- Cloud sync of user dictionary
- Fcitx5 port
- Wayland-native overlay (wlr-layer-shell)
