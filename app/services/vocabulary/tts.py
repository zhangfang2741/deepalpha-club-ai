"""Azure 神经 TTS：把单词合成高质量发音。

走服务端中转，Azure 订阅 key 只放在后端环境变量里、不下发到客户端。客户端选择
「高清」发音源时请求 `/vocabulary/tts`，由这里调用 Azure 语音服务返回 mp3。
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import logger

# Azure 语音 REST 合成接口路径（区域拼在 host 上）。
_AZURE_TTS_PATH = "cognitiveservices/v1"
# 输出 mp3，和有道/Google 源保持一致，客户端 AVAudioPlayer 直接播放并缓存。
_OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
_TIMEOUT_SECONDS = 10.0


class TTSNotConfiguredError(Exception):
    """Azure 语音服务未配置（缺 key 或 region）。"""


class TTSSynthesisError(Exception):
    """Azure TTS 合成失败（网络/鉴权/服务端错误）。"""


def _voice_for_accent(accent: str) -> str:
    """按口音选 Azure 语音名，英音用 UK 语音，其余（含 us）用 US 语音。"""
    return settings.AZURE_TTS_VOICE_UK if accent == "uk" else settings.AZURE_TTS_VOICE_US


def _build_ssml(text: str, voice: str) -> str:
    """拼 SSML。

    语言取自语音名前缀（en-US-AriaNeural → en-US）；转义 XML 特殊字符，避免用户
    输入破坏 SSML 结构。
    """
    lang = voice.rsplit("-", 1)[0] if voice.count("-") >= 2 else "en-US"
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<speak version="1.0" xml:lang="{lang}">'
        f'<voice name="{voice}">{safe}</voice>'
        "</speak>"
    )


async def synthesize_word(text: str, accent: str = "us") -> bytes:
    """调用 Azure 神经 TTS 合成单词发音，返回 mp3 字节。

    Args:
        text: 要发音的单词/短语。
        accent: "us" 或 "uk"，决定用哪个 Azure 语音。

    Returns:
        mp3 音频字节。

    Raises:
        TTSNotConfiguredError: 未配置 Azure key/region。
        TTSSynthesisError: 合成失败或返回空音频。
    """
    if not settings.AZURE_SPEECH_KEY or not settings.AZURE_SPEECH_REGION:
        raise TTSNotConfiguredError("Azure 语音服务未配置")

    voice = _voice_for_accent(accent)
    ssml = _build_ssml(text, voice)
    url = f"https://{settings.AZURE_SPEECH_REGION}.tts.speech.microsoft.com/{_AZURE_TTS_PATH}"
    headers = {
        "Ocp-Apim-Subscription-Key": settings.AZURE_SPEECH_KEY,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": _OUTPUT_FORMAT,
        "User-Agent": "deepalpha-wordlens",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, headers=headers, content=ssml.encode("utf-8"))
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("azure_tts_failed", accent=accent, voice=voice)
        raise TTSSynthesisError("Azure TTS 合成失败") from exc

    audio = resp.content
    if not audio:
        raise TTSSynthesisError("Azure TTS 返回空音频")
    logger.info("azure_tts_succeeded", accent=accent, voice=voice, bytes=len(audio))
    return audio
