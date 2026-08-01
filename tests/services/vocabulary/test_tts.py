"""MiniMax Speech HD 服务单元测试（mock httpx，不触网）。"""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.vocabulary import tts


class _FakeCircuitCache:
    """可推进时间的内存 TTL 缓存，用于隔离熔断测试。"""

    def __init__(self):
        self.now = 0
        self.values: dict[str, tuple[int, str]] = {}

    async def get(self, key: str) -> str | None:
        entry = self.values.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self.now >= expires_at:
            self.values.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self.values[key] = (self.now + (ttl or 60), value)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def advance(self, seconds: int) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def circuit_cache(monkeypatch) -> _FakeCircuitCache:
    cache = _FakeCircuitCache()
    monkeypatch.setattr(tts, "cache_service", cache)
    return cache


class _FakeClient:
    """假的 httpx.AsyncClient，支持 async with 并记录请求。"""

    def __init__(self, response=None, responses=None, error: Exception | None = None):
        self._response = response
        self._responses = list(responses or [])
        self._error = error
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        self.post_calls.append((args, kwargs))
        if self._error is not None:
            raise self._error
        if self._responses:
            return self._responses.pop(0)
        return self._response


def _success_response(audio: bytes = b"MP3DATA") -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "data": {"audio": audio.hex(), "status": 2},
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }
    return response


def _rejected_response(status_code: int) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "data": {"audio": "", "status": 1},
        "base_resp": {"status_code": status_code, "status_msg": "rejected"},
    }
    return response


def _configure_minimax(monkeypatch) -> None:
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_API_KEY", "minimax-key")
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_API_KEYS", ["minimax-key"])
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_BASE_URL", "https://api.minimaxi.com/v1")
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_MODEL", "speech-2.8-hd")
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_KEY_COOLDOWN_SECONDS", 1800)
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_VOICE_US", "English_Trustworthy_Man")
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_VOICE_UK", "English_Graceful_Lady")


def test_voice_for_accent_uses_configured_uk_and_us_voices(monkeypatch):
    _configure_minimax(monkeypatch)
    assert tts._voice_for_accent("uk") == "English_Graceful_Lady"
    assert tts._voice_for_accent("us") == "English_Trustworthy_Man"
    assert tts._voice_for_accent("") == "English_Trustworthy_Man"


async def test_synthesize_speech_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_API_KEY", "")
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_API_KEYS", [])
    with pytest.raises(tts.TTSNotConfiguredError):
        await tts.synthesize_speech("hello")


async def test_synthesize_speech_returns_hd_audio_and_expected_payload(monkeypatch):
    _configure_minimax(monkeypatch)
    client = _FakeClient(response=_success_response())

    with patch("app.services.vocabulary.tts.httpx.AsyncClient", return_value=client):
        audio = await tts.synthesize_speech("This is a complete example sentence.", "us")

    assert audio == b"MP3DATA"
    args, kwargs = client.post_calls[0]
    assert args[0] == "https://api.minimaxi.com/v1/t2a_v2"
    assert kwargs["json"]["model"] == "speech-2.8-hd"
    assert kwargs["json"]["language_boost"] == "English"
    assert kwargs["json"]["voice_setting"]["voice_id"] == "English_Trustworthy_Man"
    assert kwargs["json"]["voice_setting"]["emotion"] == "fluent"
    assert kwargs["json"]["audio_setting"]["sample_rate"] == 44100
    assert kwargs["json"]["audio_setting"]["bitrate"] == 256000


async def test_synthesize_speech_rejects_provider_error(monkeypatch):
    _configure_minimax(monkeypatch)
    response = _rejected_response(status_code=1008)

    with patch(
        "app.services.vocabulary.tts.httpx.AsyncClient",
        return_value=_FakeClient(response=response),
    ):
        with pytest.raises(tts.TTSSynthesisError):
            await tts.synthesize_speech("hello")


async def test_synthesize_speech_rejects_invalid_audio_hex(monkeypatch):
    _configure_minimax(monkeypatch)
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "data": {"audio": "not-hex", "status": 2},
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }

    with patch(
        "app.services.vocabulary.tts.httpx.AsyncClient",
        return_value=_FakeClient(response=response),
    ):
        with pytest.raises(tts.TTSSynthesisError):
            await tts.synthesize_speech("hello")


async def test_synthesize_speech_wraps_http_error(monkeypatch):
    _configure_minimax(monkeypatch)
    error = httpx.ConnectError("boom")

    with patch(
        "app.services.vocabulary.tts.httpx.AsyncClient",
        return_value=_FakeClient(error=error),
    ):
        with pytest.raises(tts.TTSSynthesisError):
            await tts.synthesize_speech("hello")


async def test_synthesize_speech_uses_next_key_after_quota_exhausted(monkeypatch):
    _configure_minimax(monkeypatch)
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_API_KEYS", ["plan-key", "paygo-key"])
    client = _FakeClient(
        responses=[
            _rejected_response(status_code=2056),
            _success_response(audio=b"SECOND_KEY_AUDIO"),
        ]
    )

    with patch("app.services.vocabulary.tts.httpx.AsyncClient", return_value=client):
        audio = await tts.synthesize_speech("hello")

    assert audio == b"SECOND_KEY_AUDIO"
    assert len(client.post_calls) == 2
    assert client.post_calls[0][1]["headers"]["Authorization"] == "Bearer plan-key"
    assert client.post_calls[1][1]["headers"]["Authorization"] == "Bearer paygo-key"


async def test_synthesize_speech_skips_exhausted_key_during_cooldown(monkeypatch):
    _configure_minimax(monkeypatch)
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_API_KEYS", ["plan-key", "paygo-key"])
    client = _FakeClient(
        responses=[
            _rejected_response(status_code=2056),
            _success_response(audio=b"FIRST_PAYGO_AUDIO"),
            _success_response(audio=b"SECOND_PAYGO_AUDIO"),
        ]
    )

    with patch("app.services.vocabulary.tts.httpx.AsyncClient", return_value=client):
        first_audio = await tts.synthesize_speech("hello")
        second_audio = await tts.synthesize_speech("world")

    assert first_audio == b"FIRST_PAYGO_AUDIO"
    assert second_audio == b"SECOND_PAYGO_AUDIO"
    assert len(client.post_calls) == 3
    assert client.post_calls[2][1]["headers"]["Authorization"] == "Bearer paygo-key"


async def test_synthesize_speech_retries_key_after_cooldown(monkeypatch, circuit_cache):
    _configure_minimax(monkeypatch)
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_API_KEYS", ["plan-key", "paygo-key"])
    client = _FakeClient(
        responses=[
            _rejected_response(status_code=2056),
            _success_response(audio=b"PAYGO_AUDIO"),
            _success_response(audio=b"RECOVERED_PLAN_AUDIO"),
        ]
    )

    with patch("app.services.vocabulary.tts.httpx.AsyncClient", return_value=client):
        await tts.synthesize_speech("hello")
        circuit_cache.advance(1801)
        recovered_audio = await tts.synthesize_speech("world")

    assert recovered_audio == b"RECOVERED_PLAN_AUDIO"
    assert len(client.post_calls) == 3
    assert client.post_calls[2][1]["headers"]["Authorization"] == "Bearer plan-key"


async def test_synthesize_speech_raises_after_all_keys_are_rejected(monkeypatch):
    _configure_minimax(monkeypatch)
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_API_KEYS", ["plan-key", "paygo-key"])
    client = _FakeClient(
        responses=[
            _rejected_response(status_code=2056),
            _rejected_response(status_code=1004),
        ]
    )

    with patch("app.services.vocabulary.tts.httpx.AsyncClient", return_value=client):
        with pytest.raises(tts.TTSSynthesisError):
            await tts.synthesize_speech("hello")

    assert len(client.post_calls) == 2


async def test_synthesize_speech_fails_fast_when_all_keys_are_cooling(monkeypatch):
    _configure_minimax(monkeypatch)
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_API_KEYS", ["plan-key", "paygo-key"])
    client = _FakeClient(
        responses=[
            _rejected_response(status_code=2056),
            _rejected_response(status_code=2056),
        ]
    )

    with patch("app.services.vocabulary.tts.httpx.AsyncClient", return_value=client):
        with pytest.raises(tts.TTSSynthesisError):
            await tts.synthesize_speech("hello")
        with pytest.raises(tts.TTSSynthesisError):
            await tts.synthesize_speech("world")

    assert len(client.post_calls) == 2


async def test_synthesize_speech_keeps_single_key_compatibility(monkeypatch):
    _configure_minimax(monkeypatch)
    monkeypatch.setattr(tts.settings, "MINIMAX_TTS_API_KEYS", [])
    client = _FakeClient(response=_success_response())

    with patch("app.services.vocabulary.tts.httpx.AsyncClient", return_value=client):
        audio = await tts.synthesize_speech("hello")

    assert audio == b"MP3DATA"
    assert client.post_calls[0][1]["headers"]["Authorization"] == "Bearer minimax-key"
