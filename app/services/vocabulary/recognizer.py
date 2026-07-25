"""拍照识别英语单词：调用 LLM 做图片 OCR + 音标 + 释义生成。"""
from __future__ import annotations

import base64

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.core.logging import logger
from app.services.llm.service import llm_service

# MiniMax-M2.7（本项目当前的默认模型）是纯文本模型，不支持图片输入——实测会直接
# 忽略请求里的图片内容，模型自己都会说"没看到图片"。MiniMax-M3 才是真正支持视觉
# 的模型（同一个 Anthropic 兼容接口），所以这里强制指定，不跟随全局默认模型。
_VISION_MODEL_NAME = "minimax-m3"

# 单独调大这一次调用的输出预算（不影响其它调用方共享的默认 max_tokens）：加了
# 词根+例句字段后，一张图识别 20+ 个单词时结构化输出比之前长不少。
_VISION_MAX_TOKENS = 4096

# 实测复现的真实故障：加了词根/例句字段后，图片里单词较多（20+）时 MiniMax-M3
# 有时会无视 API 层强制的 tool_choice，直接输出一大段 Markdown 文字介绍每个词，
# 而不调用工具——LangChain 的结构化输出在没有 tool call 时会静默返回 None（不抛
# 异常），导致后面 `result.words` 直接 AttributeError。在 prompt 里显式重复一遍
# "只能通过工具调用返回、禁止文字/Markdown 回答" 之后，同一张会稳定复现的测试图
# 就能稳定拿到正确的结构化结果了（只在 API 参数里设 tool_choice 不够，还得在
# prompt 正文里再强调一遍）。
_RECOGNIZE_PROMPT = (
    "你是一个英语学习助手。请识别这张图片中出现的所有值得学习的英语单词，并严格遵守：\n"
    "1. 排除纯虚词（冠词 a/an/the、介词、连词、常见代词）。\n"
    "2. 排除专有名词（品牌、产品、公司、人名、地名，如 Google、TikTok）——它们不是"
    "通用词汇，不必收录。\n"
    "3. 词组处理：用连字符连接的复合词（如 e-commerce、self-sufficient、after-sales、"
    "live-stream）视为**一个词**整体收录，不要拆开；空格分隔的词组/搭配（如 "
    "search engine、information source）请拆成其中各自的**实义词**分别收录。\n"
    "4. 把变形还原成原形（复数→单数、过去式/进行时/第三人称→动词原形），并纠正明显的"
    "拼写错误。\n"
    "5. 为每个词提供：国际音标（IPA，不含斜杠）、词性缩写（如 n./v./adj./adv.）、简洁"
    "的中文释义、词根/词缀简析（如没有明显词根可留空）、一个包含该单词的英文例句"
    "（附中文翻译）。\n"
    "6. 如果图片中没有可识别的英语单词，返回空列表。\n"
    "7. 必须只通过调用提供的工具返回结果，不要输出任何文字说明或 Markdown 格式的回答。"
)

_MAX_RECOGNIZE_ATTEMPTS = 2


class RecognizedWord(BaseModel):
    """单个识别出的单词。

    除 word 外全部允许缺省：实测长词表（30+ 词）时 MiniMax-M3 偶尔会漏填某个词
    的某个字段（如末尾某词漏了 definition_zh），如果这些字段是必填，pydantic
    校验会让整批结果直接报废——明明其它 29 个词都识别对了，用户却因为其中一个
    词缺一个字段而拿到「识别失败」。放宽成缺省空字符串后，单个词的字段缺失顶多
    让那一个词的某个字段是空的，不会拖累整批。
    """

    word: str = Field(..., description="识别出的英语单词原形")
    phonetic_ipa: str = Field(default="", description="国际音标，不含斜杠")
    part_of_speech: str = Field(default="", description="词性缩写")
    definition_zh: str = Field(default="", description="简洁中文释义")
    etymology: str = Field(default="", description="词根/词缀简析，没有明显词根则留空")
    example_sentence: str = Field(default="", description="包含该单词的英文例句，附中文翻译")


class _RecognizeResult(BaseModel):
    """LLM 结构化输出的顶层容器。"""

    words: list[RecognizedWord] = Field(default_factory=list)


# 混合识别方案的 OCR 提示片段：iOS 端 Apple Vision 已对图片做过本地 OCR（印刷体
# 又快又准），把抠出的候选词作为「参考线索」拼进 prompt，和 LLM 自己看图的识别结果
# 综合。两个来源互补——Vision 对印刷体召回稳，LLM 能补 Vision 漏掉的艺术字/小字、
# 也能纠正 OCR 的拼写噪声。让模型取并集，而不是二选一。
_OCR_HINT_TEMPLATE = (
    "\n\n另外，这是设备本地 OCR 对同一张图的识别结果（对印刷体较准，供你参考补充，"
    "但可能含虚词、专有名词、少量乱码，也可能漏词）：{words}。请把你自己对图片的识别"
    "与该列表**综合取并集**去重后一并输出，不要因为某个词只在其中一个来源出现就丢弃；"
    "但上述排除与词组处理规则（虚词、专有名词、乱码噪声、复合词/搭配拆分）对合并后的"
    "结果同样适用。"
)


def _build_recognize_prompt(ocr_hint: list[str] | None) -> str:
    """拼装识别 prompt：基础指令 + 可选的本地 OCR 候选词线索。"""
    hint_words = [w.strip() for w in (ocr_hint or []) if w.strip()]
    if not hint_words:
        return _RECOGNIZE_PROMPT
    return _RECOGNIZE_PROMPT + _OCR_HINT_TEMPLATE.format(words=", ".join(hint_words))


class RecognitionFailedError(Exception):
    """图片识别失败（LLM 调用异常）。"""


async def recognize_words_from_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    ocr_hint: list[str] | None = None,
) -> list[RecognizedWord]:
    """调用视觉 LLM 识别图片中的英语单词，返回候选词列表。

    Args:
        image_bytes: 图片原始字节
        mime_type: 图片 MIME 类型
        ocr_hint: iOS 端 Apple Vision 本地 OCR 抠出的候选词，作为参考线索拼进
            prompt，与 LLM 自己看图的识别结果综合取并集。为空则退化为纯看图识别。

    Returns:
        识别出的候选单词列表（可能为空）

    Raises:
        RecognitionFailedError: LLM 调用失败
    """
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    message = HumanMessage(
        content=[
            {"type": "text", "text": _build_recognize_prompt(ocr_hint)},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}},
        ]
    )
    for attempt in range(1, _MAX_RECOGNIZE_ATTEMPTS + 1):
        try:
            result = await llm_service.call(
                [message],
                model_name=_VISION_MODEL_NAME,
                response_format=_RecognizeResult,
                max_tokens=_VISION_MAX_TOKENS,
            )
        except Exception:
            logger.exception("vocabulary_recognize_llm_call_failed", attempt=attempt)
            if attempt == _MAX_RECOGNIZE_ATTEMPTS:
                raise RecognitionFailedError("LLM 识别调用失败")
            continue

        if result is not None:
            # 长词表时模型偶尔会把某个词的 word 字段本身也吐成空字符串（不是缺失
            # 这个 key，是给了个 ""，pydantic 校验挡不住）——加入生词库后这种词
            # 在列表里就是一整行空白，只有一个描边、点不出内容。这里直接过滤掉，
            # 这种词本身没有实际信息，展示出来也没意义。
            words = [w for w in result.words if w.word.strip()]
            logger.info(
                "vocabulary_recognize_succeeded",
                word_count=len(words),
                dropped_blank=len(result.words) - len(words),
                attempt=attempt,
            )
            return words

        # 模型没有调用工具、只回了纯文本（见上面的注释），结构化输出是 None。
        # 重试一次通常就好——是否触发跟具体这次采样有关，不是稳定必现的。
        logger.warning("vocabulary_recognize_no_structured_output", attempt=attempt)

    raise RecognitionFailedError("LLM 未按预期格式返回识别结果")
