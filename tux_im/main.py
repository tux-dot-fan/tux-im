"""Entry point for `ibus-engine-tux-im`."""

from __future__ import annotations

import logging
import os
import signal
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _configure_logging() -> None:
    level = logging.DEBUG if os.environ.get("TUX_IM_DEBUG") else logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT, stream=sys.stderr)
    # IBus / GLib are very chatty at DEBUG; tone them down.
    logging.getLogger("IBus").setLevel(logging.WARNING)


def main() -> int:
    _configure_logging()
    log = logging.getLogger("tux_im")

    if "--ibus" not in sys.argv:
        print("This binary is an IBus engine. Run it via IBus.", file=sys.stderr)
        print("  ibus-daemon -drx && ibus-engine-tux-im --ibus", file=sys.stderr)
        return 1

    try:
        import gi

        gi.require_version("GObject", "2.0")
        gi.require_version("IBus", "1.0")
        from gi.repository import GLib, Gio, GObject, IBus  # noqa: F401
    except (ImportError, ValueError) as exc:
        log.error("IBus/GObject introspection not available: %s", exc)
        log.error("Install: sudo apt install python3-gi python3-ibus-1.0")
        return 2

    # Ensure the TuxEngine GObject class is registered before we hand it to the
    # factory.  Importing the module side-effect-registers via __gtype_name__.
    from tux_im.config.config import Config
    from tux_im.engine import TuxEngine  # noqa: F401
    from tux_im.input.lexicon import Lexicon
    from tux_im.shortcut import ShortcutManager

    config = Config.load()
    log.info("Loaded config from %s", config.path)

    lexicon = Lexicon.load(config)
    log.info("Loaded lexicon: pinyin=%d entries, wubi=%d entries",
             len(lexicon.pinyin), len(lexicon.wubi))

    shortcuts = ShortcutManager(config)

    # Make these available to engine instances via module globals.
    import tux_im.engine as engine_module
    engine_module._config = config
    engine_module._lexicon = lexicon
    engine_module._shortcuts = shortcuts

    # ---- Config hot-reload via GLib file monitor ----

    def _reload_config(_monitor: Gio.FileMonitor, _file_obj: Gio.File,
                      _other_file: Gio.File | None,
                      event_type: Gio.FileMonitorEvent) -> None:
        """Called by GLib when config.toml changes on disk."""
        if event_type not in (Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                              Gio.FileMonitorEvent.CREATED):
            return
        log.info("Config file changed, reloading...")
        try:
            new_config = Config.load(config.path)
        except Exception:
            log.exception("Failed to reload config, keeping old one")
            return
        engine_module._config = new_config
        # Rebuild lexicon in case dict paths changed.
        try:
            new_lexicon = Lexicon.load(new_config)
            # Flush pending user words from the old lexicon before swapping it
            # out, so any learned words accumulated during the session are
            # persisted before the new lexicon starts loading from disk.
            assert engine_module._lexicon is not None
            engine_module._lexicon._flush_now()
            engine_module._lexicon = new_lexicon
            log.info("Lexicon reloaded: pinyin=%d, wubi=%d",
                     len(new_lexicon.pinyin), len(new_lexicon.wubi))
        except Exception:
            log.exception("Failed to reload lexicon, keeping old one")
            engine_module._lexicon = lexicon
        # Rebuild shortcuts in case keybindings changed.
        try:
            new_shortcuts = ShortcutManager(new_config)
            engine_module._shortcuts = new_shortcuts
            log.info("Shortcuts rebuilt from new config")
        except Exception:
            log.exception("Failed to rebuild shortcuts, keeping old ones")
            engine_module._shortcuts = shortcuts

    gfile = Gio.File.new_for_path(str(config.path))
    monitor = gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
    if monitor is not None:
        monitor.connect("changed", _reload_config)
        log.info("Watching %s for changes", config.path)
    else:
        log.warning("Could not set up file monitor for %s -- config hot-reload disabled",
                    config.path)

    # Connect to ibus-daemon via the session bus.  IBus.init() is auto-called
    # by the python-ibus override on import.
    log.info("Connecting to IBus bus...")
    bus = IBus.Bus()
    if not bus.is_connected():
        log.error("Cannot connect to IBus daemon")
        return 3
    log.info("Connected to IBus bus")

    factory = IBus.Factory(bus=bus)
    # Component XML defined one engine with the name "tux-im".
    engine_name = "tux-im"
    factory.add_engine(engine_name, GObject.type_from_name("TuxEngine"))
    log.info("Registered engine %r with the IBus factory", engine_name)

    # Acquire the well-known bus name.
    bus_name = "org.freedesktop.IBus.TuxIM"
    result = bus.request_name(bus_name, 0)
    log.info("Requested bus name %s: %s", bus_name, result)
    if result != 1:  # DBUS_REQUEST_NAME_REPLY_PRIMARY_OWNER
        log.warning("Failed to acquire bus name (result=%s). The engine may not be reachable.", result)

    # Quitting the main loop via signal.
    #
    # IMPORTANT: IBus.main() runs a GLib MainLoop which intercepts UNIX
    # signals itself — Python-level signal.signal() handlers are NOT
    # invoked while the GLib loop is running, AND calling IBus.quit()
    # from a signal handler is unsafe because GLib APIs are not
    # async-signal-safe.
    #
    # The supported pattern is GLib.unix_signal_add() (or the newer
    # GLibUnix.signal_add()) which registers a callback that runs
    # INSIDE the main loop when the signal arrives.  We still install
    # Python-level signal.signal() as a fallback in case the engine
    # is started outside an IBus main loop (e.g. during a brief
    # startup window before IBus.main() is entered).
    def _request_quit() -> None:
        log.info("Quit requested, leaving IBus.main()")
        IBus.quit()

    def _on_signal(_sig: int, _frame: object | None) -> None:
        # Fallback for pre-main-loop windows.  Inside the main loop
        # this handler is NOT called — GLib intercepts the signal and
        # invokes the GLibUnix callback below instead.
        _request_quit()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    # Inside the main loop, GLib intercepts SIGINT/SIGTERM and
    # dispatches the registered callback.  GLibUnix.signal_add is the
    # current (non-deprecated) name; the deprecation message points
    # users there.  We try it first, fall back to GLib.unix_signal_add
    # on older platforms.
    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix  # noqa: F811
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, _request_quit)
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, _request_quit)
    except (ImportError, ValueError):
        # Older GLib — use the deprecated but still-functional API.
        log.debug("GLibUnix not available, falling back to GLib.unix_signal_add")
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, _request_quit)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, _request_quit)

    log.info("TUX IM engine running (Ctrl+C to quit)")
    IBus.main()
    log.info("TUX IM engine stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
