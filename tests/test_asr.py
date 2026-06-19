"""Tests for ASR client (network mocked)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from tux_im.asr.client import ASRClient, ASRError


@pytest.mark.asyncio
async def test_transcribe_success() -> None:
    client = ASRClient(
        endpoint="https://api.example.com/transcribe",
        api_key="sk-test",
        model="whisper-1",
        language="zh",
    )
    with respx.mock(base_url="https://api.example.com") as mock:
        route = mock.post("/transcribe").mock(
            return_value=httpx.Response(200, json={"text": "你好世界"})
        )
        result = await client.transcribe(b"fake-audio-bytes")
    assert result.text == "你好世界"
    assert result.provider == "openai"


@pytest.mark.asyncio
async def test_transcribe_no_key() -> None:
    client = ASRClient(endpoint="https://api.example.com/transcribe", api_key="")
    with pytest.raises(ASRError):
        await client.transcribe(b"x")


@pytest.mark.asyncio
async def test_transcribe_api_error() -> None:
    client = ASRClient(
        endpoint="https://api.example.com/transcribe",
        api_key="sk-test",
    )
    with respx.mock(base_url="https://api.example.com") as mock:
        mock.post("/transcribe").mock(return_value=httpx.Response(401, text="bad key"))
        with pytest.raises(ASRError):
            await client.transcribe(b"x")
