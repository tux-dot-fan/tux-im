# Architecture

## Process Model

TUX IM runs as a single IBus engine process spawned by `ibus-daemon` per active IME session. A separate `tux-im-setup` GUI process provides configuration.

```
ibus-daemon
  └─ ibus-engine-tux-im --ibus  (engine.py)
  └─ tux-im-setup  (config GUI, run by user)
```

## Class Hierarchy

```
IBus.Engine
  └── TuxEngine                    [tux_im/engine.py]
        ├── self.mode: InputMode   [active input mode]
        ├── self.shortcuts: ShortcutManager
        ├── self.asr: ASRHandler
        └── self.config: Config

InputMode (Protocol)               [tux_im/input/base.py]
  ├── PinyinMode                   [tux_im/input/pinyin.py]
  ├── WubiMode                     [tux_im/input/wubi.py]
  ├── WbpyMode                     [tux_im/input/wbpy.py]
  └── LatinMode                    [tux_im/input/latin.py]

Trie                              [tux_im/input/lexicon.py]
  ├── PinyinTrie
  └── WubiTrie

ASRHandler                        [tux_im/asr/__init__.py]
  ├── ASRClient (provider)         [tux_im/asr/client.py]
  ├── AudioCapture                 [tux_im/asr/capture.py]
  └── OverlayWindow                [tux_im/asr/overlay.py]

Config                            [tux_im/config/config.py]
  ├── ShortcutManager              [tux_im/shortcut.py]
  └── FileMonitor                  [tux_im/config/monitor.py]
```

## State Machines

### Engine state

```
INITIALIZED
   ↓ focus_in
ACTIVE (with active mode)
   ↓ focus_out / disable
INACTIVE
```

### Input mode state (per keystroke)

```
EMPTY ─key→ BUFFERING ─key→ BUFFERING ─commit→ EMPTY
                         ─key(escape)→ EMPTY
                         ─key(delete)→ BUFFERING (shorter) / EMPTY
```

### ASR state

```
IDLE ─Ctrl+`→ RECORDING ─Ctrl+` / silence→ PROCESSING ─done→ RESULT
                                                              ↓
                                                           (Enter)
                                                              ↓
                                                            IDLE
```

## Threading

- **Main thread** — IBus event loop (GLib main loop)
- **ASR audio capture thread** — PyAudio callback / sounddevice InputStream
- **ASR API request thread** — `httpx` async client with asyncio

Communication back to main thread: `GLib.idle_add()` for GTK/IBus updates.

## DBus / Inter-Process Communication

The engine is registered with IBus via standard `IBus.Engine` interface on the session bus. No custom DBus methods are needed; configuration is via file.

## Error Handling

- IBus engine must never crash the daemon — all exceptions caught at `process_key_event` boundary
- ASR failures fall back gracefully (overlay shows error, doesn't commit anything)
- Config errors logged, fall back to defaults
