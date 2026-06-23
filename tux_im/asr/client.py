"""ASR API client.

Pluggable provider interface.  Default provider posts audio to an
OpenAI-compatible transcription endpoint.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx

log = logging.getLogger(__name__)


@dataclass
class ASRResult:
    text: str
    alternatives: list[str] = field(default_factory=list)
    language: str = ""
    provider: str = ""


class ASRError(Exception):
    pass


class ASRClient:
    """Thin wrapper over `httpx` for the chosen ASR provider."""

    def __init__(
        self,
        endpoint: str,
        api_key: str = "",
        model: str = "whisper-1",
        language: str = "zh",
        timeout: float = 30.0,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        self.language = language
        self.timeout = timeout

    async def transcribe(
        self, audio: bytes, filename: str = "audio.wav", content_type: str = "audio/wav"
    ) -> ASRResult:
        if not self.api_key:
            raise ASRError("No ASR API key configured")

        files = {"file": (filename, audio, content_type)}
        data = {"model": self.model, "language": self.language}
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.endpoint, headers=headers, files=files, data=data
            )
        if resp.status_code >= 400:
            raise ASRError(f"ASR API error {resp.status_code}: {resp.text}")
        try:
            payload = resp.json()
        except Exception as exc:
            raise ASRError(f"Invalid ASR response: {exc}") from exc
        text = payload.get("text", "").strip()
        if not text:
            raise ASRError("ASR returned empty text")
        log.info("ASR transcribed %d chars", len(text))
        return ASRResult(text=text, language=self.language, provider="openai")
