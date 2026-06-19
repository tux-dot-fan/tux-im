"""File monitor for hot-reloading config."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gio  # noqa: E402

log = logging.getLogger(__name__)


class FileMonitor:
    """Watch a single file and call `on_change` on every modification.

    Uses `Gio.FileMonitor` (inotify backend on Linux) to avoid polling.
    """

    def __init__(self, path: Path, on_change: Callable[[], None]) -> None:
        self._path = path
        self._on_change = on_change
        self._monitor: Gio.FileMonitor | None = None

    def start(self) -> None:
        if not self._path.exists():
            # Watch the parent directory for the file to appear.
            parent = Gio.File.new_for_path(str(self._path.parent))
            self._monitor = parent.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        else:
            f = Gio.File.new_for_path(str(self._path))
            self._monitor = f.monitor_file(Gio.FileMonitorFlags.NONE, None)
        if self._monitor is None:
            log.warning("Could not create file monitor for %s", self._path)
            return
        self._monitor.connect("changed", self._on_file_changed)

    def stop(self) -> None:
        if self._monitor is not None:
            self._monitor.cancel()

    def _on_file_changed(self, monitor, file, other_file, event_type) -> None:
        if event_type in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CREATED):
            log.info("Config file changed: %s", self._path)
            try:
                self._on_change()
            except Exception:  # pragma: no cover
                log.exception("on_change callback failed")
