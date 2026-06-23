"""High-level ASR handler: ties together client, capture, overlay, and engine commit."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from enum import StrEnum

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from tux_im.asr.capture import AudioCapture
from tux_im.asr.client import ASRClient, ASRError
from tux_im.asr.overlay import OverlayState, OverlayWindow
from tux_im.config.config import Config

log = logging.getLogger(__name__)


class ASRState(StrEnum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    RESULT = "result"


class ASRHandler:
    """Coordinates the ASR subsystem.

    - `start()` begins recording and shows the overlay.
    - `stop()` ends recording, sends audio to the API, and displays the result.
    - `commit()` commits the current transcript to the focused app via callback.
    - `cancel()` discards everything and hides the overlay.
    """

    def __init__(self, config: Config, on_commit: Callable[[str], None]) -> None:
        self._config = config
        self._on_commit = on_commit  # callable(str)
        self._client = ASRClient(
            endpoint=config.asr.api_endpoint,
            api_key=config.asr.api_key,
            model=config.asr.model,
            language=config.asr.language,
            timeout=config.asr.timeout,
        )
        self._overlay = OverlayWindow()
        self._capture = AudioCapture(
            sample_rate=config.asr.sample_rate,
            channels=config.asr.channels,
            silence_timeout=config.asr.silence_timeout,
            max_duration=config.asr.max_duration,
            on_silence=self._on_silence,
            on_level=self._on_level,
        )
        self._state = ASRState.IDLE
        self._alternatives: list[str] = []
        self._selected_index = 0
        self._tick_id: int | None = None
        self._loop = asyncio.new_event_loop()

    # ---- public API ----

    def start(self) -> None:
        if self._state != ASRState.IDLE:
            log.warning("ASR start ignored, state=%s", self._state)
            return
        log.info("ASR: starting recording")
        try:
            self._capture.start()
        except Exception as exc:
            log.error("Cannot start audio capture: %s", exc)
            self._overlay.set_state(OverlayState.RESULT, f"❌ 无法启动麦克风: {exc}")
            self._overlay.show_at_cursor()
            self._state = ASRState.RESULT
            return
        self._overlay.set_state(OverlayState.RECORDING)
        self._overlay.show_at_cursor()
        self._state = ASRState.RECORDING
        # Periodic tick to enforce silence / max duration.
        self._tick_id = GLib.timeout_add(100, self._tick)

    def stop(self) -> None:
        if self._state != ASRState.RECORDING:
            log.debug("ASR stop ignored, state=%s", self._state)
            return
        log.info("ASR: stopping recording, sending to API")
        if self._tick_id is not None:
            GLib.source_remove(self._tick_id)
            self._tick_id = None
        audio = self._capture.stop()
        self._overlay.set_state(OverlayState.PROCESSING)
        self._state = ASRState.PROCESSING
        threading.Thread(target=self._transcribe_worker, args=(audio,), daemon=True).start()

    def cancel(self) -> None:
        log.info("ASR: cancel")
        if self._state == ASRState.RECORDING:
            self._capture.stop()
        if self._tick_id is not None:
            GLib.source_remove(self._tick_id)
            self._tick_id = None
        self._overlay.hide()
        self._state = ASRState.IDLE

    def commit(self) -> None:
        if self._state != ASRState.RESULT:
            return
        text = self._overlay.get_transcript().strip()
        if text and self._on_commit:
            self._on_commit(text)
        self._overlay.hide()
        self._state = ASRState.IDLE

    def cycle_alternative(self) -> None:
        if not self._alternatives:
            return
        self._selected_index = (self._selected_index + 1) % len(self._alternatives)
        self._overlay.set_transcript(self._alternatives[self._selected_index])

    def edit_transcript(self, new_text: str) -> None:
        self._overlay.set_transcript(new_text)

    def state(self) -> ASRState:
        return self._state

    def overlay(self) -> OverlayWindow:
        return self._overlay

    # ---- internals ----

    def _tick(self) -> bool:
        self._capture.tick()
        if self._state == ASRState.RECORDING and not self._capture.is_active():
            # Silence/timeout triggered stop.
            self.stop()
            return False
        return self._state == ASRState.RECORDING

    def _on_silence(self) -> None:
        GLib.idle_add(self._on_silence_main)

    def _on_silence_main(self) -> None:
        if self._state == ASRState.RECORDING:
            self.stop()

    def _on_level(self, fraction: float) -> None:
        GLib.idle_add(self._overlay.set_level, fraction)

    def _transcribe_worker(self, audio: bytes) -> None:
        try:
            result = self._loop.run_until_complete(self._client.transcribe(audio))
        except ASRError as exc:
            log.error("ASR error: %s", exc)
            GLib.idle_add(self._on_transcribe_failed, str(exc))
            return
        except Exception as exc:  # pragma: no cover
            log.exception("ASR unexpected error")
            GLib.idle_add(self._on_transcribe_failed, str(exc))
            return
        GLib.idle_add(self._on_transcribe_done, result.text)

    def _on_transcribe_done(self, text: str) -> None:
        log.info("ASR result: %r", text)
        self._alternatives = [text]
        self._selected_index = 0
        self._overlay.set_state(OverlayState.RESULT, text)
        self._overlay.set_alternatives([])
        self._state = ASRState.RESULT

    def _on_transcribe_failed(self, error: str) -> None:
        self._overlay.set_state(OverlayState.RESULT, f"❌ {error}")
        self._state = ASRState.RESULT
