# TUX IM

[![CI](https://github.com/tux-im/tux-im/actions/workflows/ci.yml/badge.svg)](https://github.com/tux-im/tux-im/actions/workflows/ci.yml)

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

### Debian / Ubuntu (recommended)

Download the latest `.deb` from the
[Releases page](https://github.com/tux-im/tux-im/releases) and install:

```bash
sudo apt install ./tux-im_*_all.deb
ibus restart
```

The `.deb` is built automatically by CI on every tagged release; the
workflow also attaches it as a release asset.

### From source (pip)

```bash
sudo apt install ibus python3-gi python3-ibus-1.0
pip install --user tux-im
ibus restart
```

Then enable "TUX IM" in IBus preferences.

### Building the .deb from source

```bash
sudo apt install debhelper devscripts dh-sequence-python3 \
                 pybuild-plugin-pyproject python3-all
dpkg-buildpackage -us -uc -b
sudo apt install ../tux-im_*_all.deb
```

## Documentation

- [Design](docs/DESIGN.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Configuration](docs/CONFIGURATION.md)
- [Development](docs/DEVELOPMENT.md)

## License

GPL-3.0-or-later
