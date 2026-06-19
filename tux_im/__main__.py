"""Allow `python3 -m tux_im` to launch the IBus engine."""

from tux_im.main import main

if __name__ == "__main__":
    raise SystemExit(main())
