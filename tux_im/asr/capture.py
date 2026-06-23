"""Audio capture from the default microphone."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import cast

log = logging.getLogger(__name__)

try:
    import numpy as np  # type: ignore[misc]
    import sounddevice as sd  # type: ignore[misc]
    _HAVE_SD = True
except ImportError:  # pragma: no cover
    sd = None  # type: ignore[misc]
    np = None  # type: ignore[misc]
    _HAVE_SD = False


class AudioCapture:
    """Records audio from the default mic into a `bytes` buffer.

    The buffer is a 16-bit PCM WAV stream suitable for sending directly
    to an OpenAI-compatible transcription API.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        silence_timeout: float = 2.0,
        max_duration: int = 60,
        on_silence: Callable[[], None] | None = None,
        on_level: Callable[[float], None] | None = None,
    ) -> None:
        if not _HAVE_SD:
            raise RuntimeError("sounddevice/numpy not available")
        self.sample_rate = sample_rate
        self.channels = channels
        self.silence_timeout = silence_timeout
        self.max_duration = max_duration
        self.on_silence = on_silence
        self.on_level = on_level
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._last_voice = 0.0
        self._start_time = 0.0
        self._stopped = threading.Event()

    def start(self) -> None:
        with self._lock:
            self._frames.clear()
            self._last_voice = time.monotonic()
            self._start_time = time.monotonic()
            self._stopped.clear()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=self._on_audio,
        )
        self._stream.start()

    def stop(self) -> bytes:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            pcm = np.concatenate(self._frames) if self._frames else np.zeros(0, dtype=np.int16)
            self._frames.clear()
        return self._to_wav(pcm)

    def is_active(self) -> bool:
        return self._stream is not None and not self._stopped.is_set()

    def tick(self) -> None:
        """Call periodically (e.g. from GLib.timeout) to enforce silence/timeout."""
        if not self.is_active():
            return
        now = time.monotonic()
        if now - self._last_voice > self.silence_timeout:
            log.info("Silence timeout, stopping capture")
            self._stopped.set()
            if self.on_silence:
                self.on_silence()
        elif now - self._start_time > self.max_duration:
            log.info("Max duration reached, stopping capture")
            self._stopped.set()
            if self.on_silence:
                self.on_silence()

    # ---- internals ----

    def _on_audio(self, indata: object, frames: int, time_info: object, status: object) -> None:
        if status:
            log.debug("audio status: %s", status)
        chunk = cast("np.ndarray", indata).copy().reshape(-1)
        with self._lock:
            self._frames.append(chunk)
        # Compute RMS for level meter + VAD.
        rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
        if rms > 500:  # simple VAD threshold
            self._last_voice = time.monotonic()
        if self.on_level:
            try:
                self.on_level(min(1.0, rms / 8000.0))
            except Exception:  # pragma: no cover
                pass

    @staticmethod
    def _to_wav(pcm: np.ndarray) -> bytes:
        if len(pcm) == 0:
            return b""
        # Use stdlib wave to avoid extra deps.
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(16000)
            wf.writeframes(pcm.tobytes())
        return buf.getvalue()
