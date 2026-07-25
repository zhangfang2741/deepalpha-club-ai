"""拍照识别英语单词：调用 LLM 做图片 OCR + 音标 + 释义生成。"""
from __future__ import annotations

import base64

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.core.logging import logger
from app.services.llm.service import llm_service

_RECOGNIZE_PROMPT = (
    "你是一个英语学习助手。请识别这张图片中出现的所有英语单词（排除纯虚词，如冠词 "
    "a/an/the、介词、连词），为每个单词提供：国际音标（IPA，不含斜杠）、词性缩写"
    "（如 n./v./adj./adv.）、简洁的中文释义。如果图片中没有可识别的英语单词，返回空列表。"
)


class RecognizedWord(BaseModel):
    """单个识别出的单词。"""

    word: str = Field(..., description="识别出的英语单词原形")
    phonetic_ipa: str = Field(..., description="国际音标，不含斜杠")
    part_of_speech: str = Field(..., description="词性缩写")
    definition_zh: str = Field(..., description="简洁中文释义")


class _RecognizeResult(BaseModel):
    """LLM 结构化输出的顶层容器。"""

    words: list[RecognizedWord] = Field(default_factory=list)


class RecognitionFailedError(Exception):
    """图片识别失败（LLM 调用异常）。"""


async def recognize_words_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> list[RecognizedWord]:
    """调用 LLM 识别图片中的英语单词，返回候选词列表。

    Args:
        image_bytes: 图片原始字节
        mime_type: 图片 MIME 类型

    Returns:
        识别出的候选单词列表（可能为空）

    Raises:
        RecognitionFailedError: LLM 调用失败
    """
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    message = HumanMessage(
        content=[
            {"type": "text", "text": _RECOGNIZE_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}},
        ]
    )
    try:
        result = await llm_service.call([message], response_format=_RecognizeResult)
    except Exception as exc:
        logger.exception("vocabulary_recognize_llm_call_failed")
        raise RecognitionFailedError("LLM 识别调用失败") from exc

    logger.info("vocabulary_recognize_succeeded", word_count=len(result.words))
    return result.words
