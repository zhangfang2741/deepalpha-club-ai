"""MiniMax Speech HD：为 WordLens 合成高清英文例句发音。

所有请求都经服务端中转，MiniMax API Key 不下发到客户端。返回统一的 MP3 音频，
iOS 使用 AVAudioPlayer 播放并按文本、口音和用途缓存。
"""
from __future__ import annotations

import httpx

from app.core.cache import cache_key, cache_service
from app.core.config import settings
from app.core.logging import logger

_TIMEOUT_SECONDS = 20.0
_CIRCUIT_BREAKER_PROVIDER_CODES = {2056}
_CIRCUIT_BREAKER_HTTP_STATUSES = {401, 403, 429}
_SAMPLE_RATE = 44_100
_BITRATE = 256_000
_SENTENCE_EMOTION = "fluent"


class TTSNotConfiguredError(Exception):
    """MiniMax Speech 未配置 API Key。"""


class TTSSynthesisError(Exception):
    """语音合成失败（网络、鉴权、响应格式或服务端错误）。"""


def _voice_for_accent(accent: str) -> str:
    """按口音选择 MiniMax 音色；未知值统一按美音处理。"""
    return settings.MINIMAX_TTS_VOICE_UK if accent == "uk" else settings.MINIMAX_TTS_VOICE_US


def _configured_api_keys() -> list[str]:
    """返回去重后的有序 TTS Key，并兼容原有单 Key 配置。"""
    configured_keys = getattr(settings, "MINIMAX_TTS_API_KEYS", [])
    keys = [key.strip() for key in configured_keys if key.strip()]
    if not keys and settings.MINIMAX_TTS_API_KEY.strip():
        keys = [settings.MINIMAX_TTS_API_KEY.strip()]
    return list(dict.fromkeys(keys))


def _circuit_cache_key(api_key: str) -> str:
    """生成不暴露 API Key 原文的熔断缓存键。"""
    return cache_key("minimax_tts_key_circuit", api_key)


async def _is_key_circuit_open(api_key: str) -> bool:
    """判断 Key 是否仍在冷却期内。"""
    return await cache_service.get(_circuit_cache_key(api_key)) is not None


async def _open_key_circuit(api_key: str, reason: str) -> None:
    """按配置的冷却时间熔断 Key；缓存层可自动使用 Valkey 或进程内存。"""
    cooldown_seconds = settings.MINIMAX_TTS_KEY_COOLDOWN_SECONDS
    if cooldown_seconds <= 0:
        return
    await cache_service.set(
        _circuit_cache_key(api_key),
        reason,
        ttl=cooldown_seconds,
    )


async def synthesize_speech(text: str, accent: str = "us") -> bytes:
    """使用 MiniMax Speech HD 合成完整英文例句，返回高码率 MP3 字节。"""
    api_keys = _configured_api_keys()
    if not api_keys:
        raise TTSNotConfiguredError("MiniMax Speech 未配置")

    voice = _voice_for_accent(accent)
    url = f"{settings.MINIMAX_TTS_BASE_URL}/t2a_v2"
    payload = {
        "model": settings.MINIMAX_TTS_MODEL,
        "text": text,
        "stream": False,
        "language_boost": "English",
        "output_format": "hex",
        "voice_setting": {
            "voice_id": voice,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
            "emotion": _SENTENCE_EMOTION,
        },
        "audio_setting": {
            "sample_rate": _SAMPLE_RATE,
            "bitrate": _BITRATE,
            "format": "mp3",
            "channel": 1,
        },
    }

    key_count = len(api_keys)
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        for key_index, api_key in enumerate(api_keys, start=1):
            if await _is_key_circuit_open(api_key):
                logger.info(
                    "minimax_tts_key_circuit_skipped",
                    accent=accent,
                    voice=voice,
                    key_index=key_index,
                    key_count=key_count,
                )
                continue

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                http_status = (
                    exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                )
                if http_status in _CIRCUIT_BREAKER_HTTP_STATUSES:
                    await _open_key_circuit(api_key, f"http_{http_status}")
                logger.exception(
                    "minimax_tts_key_request_failed",
                    accent=accent,
                    voice=voice,
                    key_index=key_index,
                    key_count=key_count,
                    status_code=http_status,
                )
                continue

            base_response = body.get("base_resp", {})
            audio_hex = body.get("data", {}).get("audio", "")
            if base_response.get("status_code") != 0 or not audio_hex:
                status_code = base_response.get("status_code")
                if status_code in _CIRCUIT_BREAKER_PROVIDER_CODES:
                    await _open_key_circuit(api_key, f"provider_{status_code}")
                logger.warning(
                    "minimax_tts_key_rejected",
                    accent=accent,
                    voice=voice,
                    key_index=key_index,
                    key_count=key_count,
                    status_code=status_code,
                )
                continue

            try:
                audio = bytes.fromhex(audio_hex)
            except ValueError:
                logger.exception(
                    "minimax_tts_audio_decode_failed",
                    accent=accent,
                    voice=voice,
                    key_index=key_index,
                    key_count=key_count,
                )
                continue

            if not audio:
                logger.warning(
                    "minimax_tts_empty_audio",
                    accent=accent,
                    voice=voice,
                    key_index=key_index,
                    key_count=key_count,
                )
                continue

            logger.info(
                "minimax_tts_succeeded",
                accent=accent,
                voice=voice,
                key_index=key_index,
                key_count=key_count,
                bytes=len(audio),
            )
            return audio

    raise TTSSynthesisError("所有 MiniMax Speech Key 均未返回可用音频")
