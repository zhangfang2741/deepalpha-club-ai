"""Azure 神经 TTS 服务单元测试（mock httpx，不触网）。"""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.vocabulary import tts


class _FakeClient:
    """假的 httpx.AsyncClient，支持 async with 并返回预置响应或抛错。"""

    def __init__(self, response=None, error: Exception | None = None):
        self._response = response
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        if self._error is not None:
            raise self._error
        return self._response


def test_voice_for_accent_picks_uk_only_for_uk(monkeypatch):
    monkeypatch.setattr(tts.settings, "AZURE_TTS_VOICE_US", "en-US-AriaNeural")
    monkeypatch.setattr(tts.settings, "AZURE_TTS_VOICE_UK", "en-GB-SoniaNeural")
    assert tts._voice_for_accent("uk") == "en-GB-SoniaNeural"
    assert tts._voice_for_accent("us") == "en-US-AriaNeural"
    # 未知口音回退到美音，不抛错。
    assert tts._voice_for_accent("") == "en-US-AriaNeural"


def test_build_ssml_wraps_voice_lang_and_escapes():
    ssml = tts._build_ssml("fish & chips <x>", "en-GB-SoniaNeural")
    assert 'xml:lang="en-GB"' in ssml
    assert 'name="en-GB-SoniaNeural"' in ssml
    # XML 特殊字符被转义，避免破坏 SSML。
    assert "&amp;" in ssml and "&lt;" in ssml and "&gt;" in ssml
    assert "<x>" not in ssml


async def test_synthesize_word_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(tts.settings, "AZURE_SPEECH_KEY", "")
    monkeypatch.setattr(tts.settings, "AZURE_SPEECH_REGION", "")
    with pytest.raises(tts.TTSNotConfiguredError):
        await tts.synthesize_word("hello")


async def test_synthesize_word_returns_audio_bytes(monkeypatch):
    monkeypatch.setattr(tts.settings, "AZURE_SPEECH_KEY", "k")
    monkeypatch.setattr(tts.settings, "AZURE_SPEECH_REGION", "eastus")
    resp = MagicMock()
    resp.content = b"MP3DATA"
    resp.raise_for_status = MagicMock()
    with patch("app.services.vocabulary.tts.httpx.AsyncClient", return_value=_FakeClient(response=resp)):
        audio = await tts.synthesize_word("hello", "us")
    assert audio == b"MP3DATA"


async def test_synthesize_word_raises_on_empty_audio(monkeypatch):
    monkeypatch.setattr(tts.settings, "AZURE_SPEECH_KEY", "k")
    monkeypatch.setattr(tts.settings, "AZURE_SPEECH_REGION", "eastus")
    resp = MagicMock()
    resp.content = b""
    resp.raise_for_status = MagicMock()
    with patch("app.services.vocabulary.tts.httpx.AsyncClient", return_value=_FakeClient(response=resp)):
        with pytest.raises(tts.TTSSynthesisError):
            await tts.synthesize_word("hello")


async def test_synthesize_word_wraps_http_error(monkeypatch):
    monkeypatch.setattr(tts.settings, "AZURE_SPEECH_KEY", "k")
    monkeypatch.setattr(tts.settings, "AZURE_SPEECH_REGION", "eastus")
    err = httpx.ConnectError("boom")
    with patch("app.services.vocabulary.tts.httpx.AsyncClient", return_value=_FakeClient(error=err)):
        with pytest.raises(tts.TTSSynthesisError):
            await tts.synthesize_word("hello")
