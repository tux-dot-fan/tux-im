# TUX IM

An IBus input method engine for Linux supporting:

- **Pinyin** — Standard Chinese phonetic input
- **Wubi 86** — Wangma five-stroke input
- **Wbpy** — Automatic mixed Wubi + Pinyin input
- **ASR** — Voice input via cloud API

## Features

- Uses existing RIME dictionaries when available, no need to bundle large data files
- Pluggable ASR provider (OpenAI Whisper API by default)
- Hot-reloadable TOML configuration
- GTK-based settings panel and floating ASR overlay
- Minimal dependencies (Python + GTK + IBus)

## Install

```bash
sudo apt install ibus python3-gi python3-ibus-1.0
pip install --user tux-im
ibus restart
```

Then enable "TUX IM" in IBus preferences.

## Documentation

- [Design](docs/DESIGN.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Configuration](docs/CONFIGURATION.md)
- [Development](docs/DEVELOPMENT.md)

## License

GPL-3.0-or-later
