# Configuration

## Config File

Location: `~/.config/tux-im/config.toml`

Loaded at engine start, hot-reloaded when the file changes (via `Gio.FileMonitor`).

Format: TOML.

## Full Schema

```toml
# Input method behavior
[ime]
default_mode = "pinyin"            # pinyin | wubi | wbpy
auto_punct = true                  # auto . → 。 in CN mode
full_width_default = false         # default to full-width punctuation
show_pinyin_in_preedit = true      # show pinyin above candidate
max_candidates = 9                 # candidates per page

# Keyboard shortcuts
[ime.shortcuts]
toggle_en_cn = "Caps_Lock"         # keyval name
start_asr = "<Ctrl>grave"          # Ctrl+`
commit_first = "space"             # commit first candidate
candidate_1 = "1"
candidate_2 = "2"
candidate_3 = "3"
candidate_4 = "4"
candidate_5 = "5"
candidate_6 = "6"
candidate_7 = "7"
candidate_8 = "8"
candidate_9 = "9"
page_up = "bracketleft"            # [
page_down = "bracketright"         # ]
cycle_mode = "<Ctrl><Shift>m"      # cycle pinyin/wubi/wbpy
toggle_full_width = "<Shift>space"
open_settings = "<Ctrl>comma"
cancel = "Escape"
delete_left = "BackSpace"
delete_word = "<Ctrl>BackSpace"
clear_buffer = "Escape"

# ASR / voice input
[asr]
provider = "openai"                # openai | azure | google | custom
api_endpoint = "https://api.openai.com/v1/audio/transcriptions"
api_key = ""                       # leave empty to prompt on first use
language = "zh"                    # BCP-47, e.g. "zh", "zh-CN", "en"
timeout = 30                       # seconds
sample_rate = 16000
channels = 1
silence_timeout = 2.0              # auto-stop after N seconds of silence
max_duration = 60                  # hard cap on recording length

# ASR provider-specific
[asr.options]
model = "whisper-1"

# UI / overlay
[ui]
theme = "system"                   # system | dark | light
overlay_position = "cursor"        # cursor | fixed
overlay_offset_x = 0
overlay_offset_y = 24
font_size = 14

# User dictionary (learned words)
[dictionary]
user_words_path = "~/.config/tux-im/user_words.txt"
learn_enabled = true
```

## Shortcut Format

Shortcut strings follow GTK accelerator format:
- `Ctrl`, `Shift`, `Alt`, `Super` — modifiers in angle brackets
- `grave` — keyval name (matches `Gdk.keyval_from_name`)
- `space`, `BackSpace`, `Escape`, etc.

Examples:
- `Caps_Lock`
- `<Ctrl>grave`
- `<Ctrl><Shift>m`
- `<Shift>space`

## Defaults

If the config file doesn't exist or is invalid, the engine falls back to built-in defaults (see `tux_im/config/config.py::DEFAULT_CONFIG`).

## Hot Reload

`FileMonitor` watches `config.toml` for `CHANGES_ONLY` events. On change:
1. Reload TOML
2. Validate schema
3. Apply non-restart-required changes (punctuation, candidates count, etc.)
4. Restart-required changes (shortcuts) trigger a soft reset of the engine

## User Dictionary

A plain text file at `~/.config/tux-im/user_words.txt` in RIME format:

```
我的词组	wo3de5ci2zu3
自定义	ziding4yi4
```

User words are merged with the system dict at load time, with user words taking priority on frequency.

## API Key Handling

- Stored in config file with `0600` permissions
- If empty, first ASR use prompts via settings panel (not in-engine, to avoid focus issues)
- Alternative: read from `OPENAI_API_KEY` env var as fallback
