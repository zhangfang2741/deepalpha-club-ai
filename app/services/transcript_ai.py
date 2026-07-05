"""财报电话会议的 AI 增强：中文总结与专业中文翻译。

- 总结：基于 prepared remarks + Q&A，产出结构化的中文要点。
- 翻译：把英文逐字稿分段翻译成中文，强调金融/股票行业专业术语的准确性。

两类结果都会按稿件 URL 缓存（逐字稿内容不可变），避免重复且昂贵的 LLM 调用。
"""

from __future__ import annotations

import asyncio
import hashlib

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.cache import cache_service
from app.core.logging import logger
from app.schemas.motley_fool import (
    TranscriptSummary,
    TranscriptSummaryResponse,
    TranscriptTranslationResponse,
)
from app.services.llm import llm_service

# 缓存 7 天：逐字稿一旦发布内容不再变化
_CACHE_TTL_SECONDS = 7 * 24 * 3600
# 单段翻译输入长度上限（字符）。MAX_TOKENS 默认 2000，控制输入以保证中文输出不被截断
_TRANSLATE_CHUNK_CHARS = 1600
# 翻译并发上限，避免瞬时打满上游速率
_TRANSLATE_CONCURRENCY = 4
# 送入总结的原文长度上限，避免超出上下文
_SUMMARY_MAX_CHARS = 24000

_SUMMARY_SYSTEM_PROMPT = """你是一名资深的股票研究分析师，擅长解读美股公司的财报电话会议（earnings call）。
请阅读下面提供的英文财报电话会议逐字稿（含管理层发言与分析师问答），用**简体中文**输出结构化摘要。

要求：
- 使用金融、股票、财务行业的专业、准确术语（如营收 revenue、毛利率 gross margin、指引 guidance、
  每股收益 EPS、自由现金流 free cash flow、同比 YoY、环比 QoQ 等）。
- 只依据逐字稿内容，不要编造未提及的数字或结论。
- 数字、涨跌幅、指标尽量保留原文口径。
- 简洁、要点化，避免空话。"""

_TRANSLATE_SYSTEM_PROMPT = """你是一名专业的金融财经翻译，精通美股财报电话会议的中英翻译。
请把用户提供的英文财报电话会议逐字稿片段翻译成**简体中文**。

要求：
- 严格忠实原文，不增删、不总结、不解释。
- 使用金融/股票/财务行业的规范中文术语（例如：revenue→营收、gross margin→毛利率、
  operating margin→营业利润率、guidance→业绩指引、EPS→每股收益、buyback→股票回购、
  free cash flow→自由现金流、backlog→在手订单、churn→流失率、YoY→同比、QoQ→环比）。
- 保留发言人姓名与职务标签（如 "Jensen Huang -- Chief Executive Officer"）及其原有格式，
  人名、公司名、产品名、股票代码保持英文原文。
- 保持原有段落结构，逐段对应翻译，不要合并或拆分段落。
- 只输出翻译后的中文正文，不要添加任何前言、注释或说明。"""


def _cache_key(kind: str, url: str) -> str:
    """基于稿件 URL 构建稳定的缓存 key。"""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    return f"transcript:{kind}:{digest}"


def _split_into_chunks(text: str, max_chars: int) -> list[str]:
    """按段落边界把长文切分为不超过 max_chars 的片段。"""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buffer: list[str] = []
    length = 0
    for paragraph in paragraphs:
        para_len = len(paragraph) + 2
        if buffer and length + para_len > max_chars:
            chunks.append("\n\n".join(buffer))
            buffer = []
            length = 0
        # 单段本身超长时，进一步按句子粗切
        if para_len > max_chars:
            for piece in _split_oversized_paragraph(paragraph, max_chars):
                chunks.append(piece)
            continue
        buffer.append(paragraph)
        length += para_len
    if buffer:
        chunks.append("\n\n".join(buffer))
    return chunks


def _split_oversized_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """把超长段落按句子边界切成多块。"""
    sentences = paragraph.replace(". ", ".\n").split("\n")
    pieces: list[str] = []
    buffer: list[str] = []
    length = 0
    for sentence in sentences:
        sent_len = len(sentence) + 1
        if buffer and length + sent_len > max_chars:
            pieces.append(" ".join(buffer))
            buffer = []
            length = 0
        buffer.append(sentence)
        length += sent_len
    if buffer:
        pieces.append(" ".join(buffer))
    return pieces


class TranscriptAIService:
    """对财报电话会议逐字稿做中文总结与翻译。"""

    async def summarize(
        self,
        ticker: str,
        title: str,
        url: str,
        prepared_remarks: str,
        questions_and_answers: str,
    ) -> TranscriptSummaryResponse:
        """生成逐字稿的结构化中文摘要（带缓存）。"""
        cache_hit = await cache_service.get(_cache_key("summary", url)) if url else None
        if cache_hit:
            logger.info("transcript_summary_cache_hit", ticker=ticker, url=url)
            summary = TranscriptSummary.model_validate_json(cache_hit)
            return TranscriptSummaryResponse(ticker=ticker, title=title, url=url, summary=summary)

        combined = self._compose_summary_input(title, prepared_remarks, questions_and_answers)
        logger.info("transcript_summary_llm_call", ticker=ticker, url=url, chars=len(combined))
        summary = await llm_service.call(
            [
                SystemMessage(content=_SUMMARY_SYSTEM_PROMPT),
                HumanMessage(content=combined),
            ],
            response_format=TranscriptSummary,
        )

        if url:
            await cache_service.set(_cache_key("summary", url), summary.model_dump_json(), ttl=_CACHE_TTL_SECONDS)
        return TranscriptSummaryResponse(ticker=ticker, title=title, url=url, summary=summary)

    async def translate(
        self,
        ticker: str,
        url: str,
        prepared_remarks: str,
        questions_and_answers: str,
    ) -> TranscriptTranslationResponse:
        """把逐字稿翻译成中文（分段并发 + 缓存）。"""
        cache_hit = await cache_service.get(_cache_key("translation", url)) if url else None
        if cache_hit:
            logger.info("transcript_translation_cache_hit", ticker=ticker, url=url)
            return TranscriptTranslationResponse.model_validate_json(cache_hit)

        logger.info(
            "transcript_translation_llm_call",
            ticker=ticker,
            url=url,
            prepared_chars=len(prepared_remarks),
            qa_chars=len(questions_and_answers),
        )
        semaphore = asyncio.Semaphore(_TRANSLATE_CONCURRENCY)
        prepared_zh, qa_zh = await asyncio.gather(
            self._translate_section(prepared_remarks, semaphore),
            self._translate_section(questions_and_answers, semaphore),
        )

        response = TranscriptTranslationResponse(
            ticker=ticker,
            url=url,
            prepared_remarks_zh=prepared_zh,
            questions_and_answers_zh=qa_zh,
        )
        if url:
            await cache_service.set(
                _cache_key("translation", url), response.model_dump_json(), ttl=_CACHE_TTL_SECONDS
            )
        return response

    def _compose_summary_input(self, title: str, prepared: str, qa: str) -> str:
        """拼接送入总结模型的原文，超长时截断 Q&A。"""
        header = f"标题：{title}\n\n" if title else ""
        body = f"【管理层发言 Prepared Remarks】\n{prepared}\n\n【问答 Q&A】\n{qa}"
        combined = header + body
        if len(combined) > _SUMMARY_MAX_CHARS:
            combined = combined[:_SUMMARY_MAX_CHARS]
        return combined

    async def _translate_section(self, text: str, semaphore: asyncio.Semaphore) -> str:
        """分段翻译一个章节，保持段落顺序。"""
        if not text.strip():
            return ""
        chunks = _split_into_chunks(text, _TRANSLATE_CHUNK_CHARS)
        results = await asyncio.gather(*(self._translate_chunk(chunk, semaphore) for chunk in chunks))
        return "\n\n".join(part for part in results if part)

    async def _translate_chunk(self, chunk: str, semaphore: asyncio.Semaphore) -> str:
        """翻译单个片段。"""
        async with semaphore:
            response = await llm_service.call(
                [
                    SystemMessage(content=_TRANSLATE_SYSTEM_PROMPT),
                    HumanMessage(content=chunk),
                ],
                temperature=0.2,
            )
        content = response.content
        return content.strip() if isinstance(content, str) else str(content).strip()


transcript_ai_service = TranscriptAIService()
