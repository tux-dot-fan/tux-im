# Development

## Setup

### System dependencies (Debian/Ubuntu)

```bash
sudo apt install ibus ibus-dev libibus-1.0-dev python3-gi python3-ibus-1.0 \
                 python3-pip python3-venv portaudio19-dev
```

### Python environment

```bash
cd tux-im
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running

### Start the engine (development)

```bash
# Stop ibus-daemon or run in isolated mode
./scripts/run-dev.sh
```

This runs `ibus-engine-tux-im --ibus` with the IBus component XML installed locally.

### Run settings panel

```bash
tux-im-setup
```

## Testing

```bash
pytest tests/
```

Tests use mock IBus / mock audio / mock ASR API.

## Code Style

- Python 3.11+
- Type hints throughout
- `ruff` for linting
- `mypy --strict` for type checking

## Logging

Uses stdlib `logging`. Set `TUX_IM_DEBUG=1` env var for verbose output.

## Building a Package

```bash
python -m build
```

Produces a wheel and sdist in `dist/`.

## Installing System-Wide

```bash
sudo cp dist/tux_im-*.whl /usr/local/lib/python3.11/dist-packages/
sudo cp setup/ibus-engine-tux-im.in /usr/libexec/ibus-engine-tux-im
sudo cp setup/com.github.tux-im.TuxIM.xml /usr/share/ibus/component/
ibus restart
```

## Debugging

```bash
TUX_IM_DEBUG=1 ibus-engine-tux-im --ibus 2>&1 | tee /tmp/tux-im.log
```

Then trigger IME in any app and inspect `/tmp/tux-im.log`.
