# TUX IM — Agent Guide

## Entry Points

- `ibus-engine-tux-im` → `tux_im.main:main` — IBus engine process
- `tux-im-setup` → `tux_im.ui.settings:main` — GTK settings panel

## Dev Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

System deps: `sudo apt install ibus ibus-dev libibus-1.0-dev python3-gi python3-ibus-1.0 python3-pip python3-venv portaudio19-dev`

## Running

```bash
TUX_IM_DEBUG=1 ibus-engine-tux-im --ibus 2>&1 | tee /tmp/tux-im.log
tux-im-setup  # settings GUI
```

## Code Quality

```bash
ruff check .
mypy --strict .
pytest tests/
```

Order matters: `ruff → mypy → pytest`

## Build

```bash
python -m build              # pip wheel+sdist → dist/
./scripts/build-deb.sh       # install deb deps, then:
dpkg-buildpackage -us -uc -b # → ../tux-im_*.deb
```

## Architecture

- `tux_im/engine.py` — `IBusEngine` subclass; `process_key_event` is the main hook (NEVER let it raise — all exceptions caught at boundary)
- `tux_im/input/` — `InputMode` protocol: `PinyinMode`, `WubiMode`, `WbpyMode`, `LatinMode`
- `tux_im/input/lexicon.py` — `PinyinTrie`, `WubiTrie` (prefix lookup for candidate generation)
- `tux_im/asr/` — ASR client, audio capture, GTK overlay window
- `tux_im/config/` — TOML config loader, `FileMonitor` for hot-reload

Config: `~/.config/tux-im/config.toml` (hot-reloaded on change via `Gio.FileMonitor`)

## Debug Logging

`TUX_IM_DEBUG=1` env var enables verbose logging. IBus/GLib are silenced to WARNING by default.

## Key Constraints

- IBus engine process: crash = daemon crash — all `process_key_event` exceptions must be caught
- ASR failures: show error in overlay, do not commit anything
- Config errors: log, fall back to defaults
- Python 3.12+ required