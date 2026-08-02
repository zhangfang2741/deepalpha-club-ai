"""拍照识别英语单词：调用 LLM 做图片 OCR + 音标 + 释义生成。

两阶段流程（而不是一次视觉调用里把"看图识词"和"逐词配 IPA/释义/词根/例句"全干
了）：
  1. 识别阶段：一次视觉 LLM 调用，只产出单词列表（不带任何附加字段），输出量
     跟词数近似线性但系数很小，100+ 词也不会撑爆 max_tokens。
  2. 丰富阶段：把识别出的词表切成小批，并发跑多个纯文本 LLM 调用（不用再看
     图），每批给 IPA/词性/释义/词根/例句。小批意味着单次调用的输出量可控，
     不会被截断；纯文本任务也比"看图识词+配释义"一把梭更容易稳定遵守工具
     调用格式。
  3. 漏词重试：首轮丰富后若仍有词 definition_zh 为空（模型对太简单的词会
     "觉得不用管"系统跳过），把没填上的词再跑一轮。两轮封顶。

这是为了解决实测复现的问题：一张图 100+ 个词时，一次性视觉调用在 max_tokens
预算耗尽后被硬截断，只能拿到前 30 出头个词（最后一个词的字段还是半截的）；
分批+重试两件事加起来，既保证了识别总量，也兜住了简单词被模型跳过的尾巴。
"""
from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from typing import TypeVar

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import logger
from app.services.llm.service import llm_service

_T = TypeVar("_T", bound=BaseModel)

# 拍照识别专用的视觉模型：不跟随全局默认模型（聊天用的 MiniMax-M2.7 等纯文本模型
# 不支持图片输入，实测会直接忽略图片说"没看到图片"）。改由 VOCAB_VISION_PROVIDER /
# VOCAB_VISION_MODEL 配置，默认 Gemini 2.5 Flash（多语言 OCR 强、秒级延迟、成本低）。
# registry.build_vision_llm() 会按配置独立构建该模型并追加进注册表，这里按名取用。
# 丰富阶段虽不需要看图，但沿用同一模型：少一个不确定性来源，Gemini Flash 处理纯文本
# 结构化输出同样又快又稳。
def _vision_model_name() -> str:
    """当前配置的视觉模型名（= registry 中追加的视觉模型条目名）。"""
    return settings.VOCAB_VISION_MODEL


_MAX_ATTEMPTS = 2

# 丰富阶段每批词数：120 词整图实测复现过，一次性丰富到「service」这个词时
# example_sentence 字段被硬截断成空——4096 tokens 撑不住太多词。15 词一批
# （每词约 100~150 tokens 输出）留了足够余量，不会重蹈覆辙。
_ENRICH_CHUNK_SIZE = 8
# 并发跑几批丰富请求；太高容易把下游 LLM API 的速率限制打爆，4 是经验值。
_ENRICH_MAX_CONCURRENCY = 4
# 重试漏词轮数上限：首轮丰富后若仍有词 definition_zh 为空（模型对太简单的词
# 会"觉得不用管"系统跳过），把没填上的词再跑一轮。两轮是经验值——再多也没用，
# 同样的词模型还是会照样跳过，只是白白消耗 token+延迟。
_ENRICH_MAX_RETRIES = 2

_IDENTIFY_PROMPT = (
    "你是一个英语学习助手。请识别这张图片中出现的所有值得学习的英语单词，并严格遵守：\n"
    "1. 排除纯虚词（冠词 a/an/the、介词、连词、常见代词）。\n"
    "2. 排除专有名词（品牌、产品、公司、人名、地名，如 Google、TikTok）——它们不是"
    "通用词汇，不必收录。\n"
    "3. 词组处理：用连字符连接的复合词（如 e-commerce、self-sufficient、after-sales、"
    "live-stream）视为**一个词**整体收录，不要拆开；空格分隔的词组/搭配（如 "
    "search engine、information source）请拆成其中各自的**实义词**分别收录。\n"
    "4. 把变形还原成原形（复数→单数、过去式/进行时/第三人称→动词原形），并纠正明显的"
    "拼写错误。\n"
    "5. 如果图片中没有可识别的英语单词，返回空列表。\n"
    "6. 必须只通过调用提供的工具返回单词列表，不要输出任何文字说明或 Markdown 格式的"
    "回答，也不要为每个词附加音标/释义等信息——这一步只要词本身。"
)

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

# 逗号顿号连接成一句话时实测会漏答（哪怕明确要求"有几个词就必须返回几个词"，
# 常见短词如 idea/world/third 这种模型会觉得"太简单不用管"，一批 8 个都能漏 3、
# 5 个）。改成逐行编号后再重复一遍数量，把"这是一份需要逐条处理的清单"这个信号
# 做得更明确，用编号任务清单的提示模式换更高的枚举覆盖率。
_ENRICH_PROMPT_TEMPLATE = (
    "你是一个英语学习助手。以下是一批已经确定要收录的英语单词原形，逐行编号：\n"
    "{numbered_words}\n"
    "请为列表中**每一个编号对应的词**都提供：国际音标（IPA，不含斜杠）、词性缩写"
    "（如 n./v./adj./adv.）、简洁的中文释义、词根/词缀简析（没有明显词根可留空）、"
    "一个包含该单词的英文例句（附中文翻译）。\n"
    "上面一共有 {count} 个词，你的回答也必须正好包含这 {count} 个词，逐一对应，"
    "不能因为某个词看起来简单常见就跳过不答，也不能额外添加列表之外的词。\n"
    "必须只通过调用提供的工具返回结果，不要输出任何文字说明或 Markdown 格式的回答。"
)


def _build_identify_prompt(ocr_hint: list[str] | None) -> str:
    """拼装识别 prompt：基础指令 + 可选的本地 OCR 候选词线索。"""
    hint_words = [w.strip() for w in (ocr_hint or []) if w.strip()]
    if not hint_words:
        return _IDENTIFY_PROMPT
    return _IDENTIFY_PROMPT + _OCR_HINT_TEMPLATE.format(words=", ".join(hint_words))


class RecognizedWord(BaseModel):
    """单个识别出的单词。

    除 word 外全部允许缺省：丰富阶段某一批调用即使彻底失败，也会用只有 word
    字段的兜底实例填回去（见 _enrich_chunk），保证这个词不会从结果里消失，
    顶多是音标/释义等字段暂时是空的。
    """

    word: str = Field(..., description="识别出的英语单词原形")
    phonetic_ipa: str = Field(default="", description="国际音标，不含斜杠")
    part_of_speech: str = Field(default="", description="词性缩写")
    definition_zh: str = Field(default="", description="简洁中文释义")
    etymology: str = Field(default="", description="词根/词缀简析，没有明显词根则留空")
    example_sentence: str = Field(default="", description="包含该单词的英文例句，附中文翻译")


class _IdentifyResult(BaseModel):
    """识别阶段的结构化输出：只有单词列表。"""

    words: list[str] = Field(default_factory=list)


class _RecognizeResult(BaseModel):
    """丰富阶段的结构化输出：带完整字段的单词列表。"""

    words: list[RecognizedWord] = Field(default_factory=list)


class RecognitionFailedError(Exception):
    """图片识别失败（LLM 调用异常）。"""


async def _call_with_retry(message: HumanMessage, response_format: type[_T]) -> _T:
    """带重试的结构化输出调用：处理"异常"和"模型没走工具调用返回 None"两种失败。

    Raises:
        RecognitionFailedError: 重试耗尽仍未拿到结果。
    """
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            result = await llm_service.call(
                [message],
                model_name=_vision_model_name(),
                response_format=response_format,
            )
        except Exception as exc:
            logger.exception("vocabulary_recognize_llm_call_failed", attempt=attempt)
            if attempt == _MAX_ATTEMPTS:
                raise RecognitionFailedError("LLM 识别调用失败") from exc
            continue

        if result is not None:
            return result

        # 模型没有调用工具、只回了纯文本，结构化输出是 None。重试一次通常就好——
        # 是否触发跟具体这次采样有关，不是稳定必现的。
        logger.warning("vocabulary_recognize_no_structured_output", attempt=attempt)

    raise RecognitionFailedError("LLM 未按预期格式返回识别结果")


async def _identify_words(image_bytes: bytes, mime_type: str, ocr_hint: list[str] | None) -> list[str]:
    """识别阶段：看图 + OCR 线索，只产出去重去噪后的单词列表。"""
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    message = HumanMessage(
        content=[
            {"type": "text", "text": _build_identify_prompt(ocr_hint)},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}},
        ]
    )
    result: _IdentifyResult = await _call_with_retry(message, _IdentifyResult)
    # 大小写不敏感去重，保留首次出现的大小写。
    seen: set[str] = set()
    words: list[str] = []
    for w in result.words:
        stripped = w.strip()
        if not stripped or stripped.lower() in seen:
            continue
        seen.add(stripped.lower())
        words.append(stripped)
    return words


async def _enrich_chunk(words: list[str], semaphore: asyncio.Semaphore) -> list[RecognizedWord]:
    """丰富阶段的一批：给这批词配 IPA/释义/词根/例句。

    这批调用整体失败，或者返回结果里缺了某几个词，都用只有 word 字段的兜底
    实例填回去——保证调用方传进来的每一个词都会出现在返回结果里。
    """
    numbered = "\n".join(f"{i}. {w}" for i, w in enumerate(words, start=1))
    message = HumanMessage(
        content=_ENRICH_PROMPT_TEMPLATE.format(numbered_words=numbered, count=len(words))
    )
    async with semaphore:
        try:
            result: _RecognizeResult = await _call_with_retry(message, _RecognizeResult)
        except RecognitionFailedError:
            logger.warning("vocabulary_enrich_chunk_failed_fallback_bare", word_count=len(words))
            return [RecognizedWord(word=w) for w in words]

    enriched_by_lower = {w.word.strip().lower(): w for w in result.words if w.word.strip()}
    missing = [w for w in words if w.lower() not in enriched_by_lower]
    if missing:
        logger.warning("vocabulary_enrich_chunk_missing_words", requested=len(words), missing=missing)
    return [enriched_by_lower.get(w.lower(), RecognizedWord(word=w)) for w in words]


async def recognize_words_from_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    ocr_hint: list[str] | None = None,
    on_partial: Callable[[list[RecognizedWord]], None] | None = None,
) -> list[RecognizedWord]:
    """识别图片中的英语单词并逐个配上音标/释义等信息。

    Args:
        image_bytes: 图片原始字节
        mime_type: 图片 MIME 类型
        ocr_hint: iOS 端 Apple Vision 本地 OCR 抠出的候选词，作为参考线索拼进
            识别阶段的 prompt，与 LLM 自己看图的识别结果综合取并集。为空则
            退化为纯看图识别。
        on_partial: 可选回调，在每个 enrich chunk（首轮或重试轮）一完成时就
            调用一次，参数是当前累积的 RecognizedWord 列表；结尾再收尾调用
            一次确保拿到的是最终态。用来给 NDJSON 流式端点推进 partial 事件。
            按 chunk 逐个上报而不是等一整轮全部跑完才报一次——124 词分 16 批、
            并发上限 4，等全部跑完可能要几十秒，逐 chunk 上报能把第一次进度
            提前到第一批完成的时候，避免用户在这几十秒里看到的是"屏幕空转"。
            回调是同步调用（不 await），上层若要跨协程消费需要自己用队列包
            一层。

    Returns:
        识别出的候选单词列表（可能为空）

    Raises:
        RecognitionFailedError: 识别阶段的 LLM 调用失败（丰富阶段单批失败不会
            让整体报错，会退化成该批词只有 word 字段）
    """
    words = await _identify_words(image_bytes, mime_type, ocr_hint)
    if not words:
        logger.info("vocabulary_recognize_succeeded", word_count=0)
        if on_partial is not None:
            on_partial([])
        return []

    chunks = [words[i : i + _ENRICH_CHUNK_SIZE] for i in range(0, len(words), _ENRICH_CHUNK_SIZE)]
    semaphore = asyncio.Semaphore(_ENRICH_MAX_CONCURRENCY)
    # 按小写合并回单条索引，便于后续按 word 原地覆盖重试结果；下面两个内嵌协程
    # 并发跑的时候都会各自 mutate 它——asyncio 单线程协作式调度，await 之间不会
    # 被抢占，多个 chunk 同时改这个 dict 不存在竞态。
    #
    # 先用只有 word 字段的裸实例把全部识别结果占好位，而不是从空 dict 逐个 chunk
    # 累加：这样每次 on_partial 推出去的词表总数从头到尾都是稳定的，只有"已配上
    # 释义"的数量在涨。若从空开始累加，前端看到的总数会先跳到全量、再掉回第一批
    # 的 8 个，数字来回倒退。
    enriched_by_lower: dict[str, RecognizedWord] = {
        w.strip().lower(): RecognizedWord(word=w) for w in words
    }

    # identify 一完成就先推一次。这一步是单次视觉 LLM 调用，实测要 15~50 秒，
    # 期间前端除了心跳收不到任何信号；如果等到第一个 enrich chunk 完成才推第一次
    # 进度，用户在最长的那段等待里看到的只能是"屏幕空转"。先把词表推出去，前端
    # 立刻能显示总词数，后面每个 chunk 再让"已配释义的词数"往上走。
    if on_partial is not None:
        on_partial(list(enriched_by_lower.values()))

    async def _run_first_pass_chunk(chunk: list[str]) -> None:
        result = await _enrich_chunk(chunk, semaphore)
        for w in result:
            key = w.word.strip().lower()
            if key:
                enriched_by_lower[key] = w
        if on_partial is not None:
            on_partial(list(enriched_by_lower.values()))

    await asyncio.gather(*(_run_first_pass_chunk(chunk) for chunk in chunks))

    async def _run_retry_chunk(chunk: list[str]) -> None:
        result = await _enrich_chunk(chunk, semaphore)
        # 覆盖式合并：重试里 definition_zh 仍是空的，按原样保留（无进展时不浪费后续调用）。
        for w in result:
            key = w.word.strip().lower()
            if not key:
                continue
            if w.definition_zh or key not in enriched_by_lower:
                enriched_by_lower[key] = w
        if on_partial is not None:
            on_partial(list(enriched_by_lower.values()))

    # 首轮丰富后 definition_zh 为空的词（典型表现：模型觉得"idea / world / Tuesday
    # 这种太简单不用写"系统跳过），把它们单独再跑一轮——换个批次的"上下文压力"，
    # 大概率能把空字段补上。两轮封顶，避免无限循环/白白烧 token。
    for attempt in range(1, _ENRICH_MAX_RETRIES + 1):
        missing = [rw.word for _, rw in enriched_by_lower.items() if not rw.definition_zh]
        if not missing:
            break
        retry_chunks = [
            missing[i : i + _ENRICH_CHUNK_SIZE] for i in range(0, len(missing), _ENRICH_CHUNK_SIZE)
        ]
        await asyncio.gather(*(_run_retry_chunk(chunk) for chunk in retry_chunks))
        logger.info(
            "vocabulary_enrich_retry_done",
            attempt=attempt,
            retried=len(missing),
            still_missing=sum(1 for rw in enriched_by_lower.values() if not rw.definition_zh),
        )

    enriched = list(enriched_by_lower.values())
    if on_partial is not None:
        on_partial(enriched)
    logger.info(
        "vocabulary_recognize_succeeded",
        word_count=len(enriched),
        identified_count=len(words),
        chunk_count=len(chunks),
    )
    return enriched
