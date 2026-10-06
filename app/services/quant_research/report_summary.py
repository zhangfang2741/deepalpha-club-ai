"""最新财报的中文要点：取原文关键章节 → 大模型整理成结构化要点 → Redis 缓存（同一份财报只生成一次、全员共用）。

大模型额度与 App 对话 / 翻译共用：每日新生成份数有上限（REPORT_SUMMARY_DAILY_LIMIT，按 UTC 日计数）、同一份财报同一时刻只生成一次（锁）、
失败短暂记一笔不重试风暴、额度用尽 / 文字无法提取都明确告知。生成放后台任务，接口立即返回 generating，客户端轮询。
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from redis.asyncio import Redis

from app.cache.operations import acquire_lock, get_json, incr_with_ttl, release_lock, set_json
from app.core.config import settings
from app.core.logging import logger
from app.schemas.quant_research import LatestReportOut, ReportSummary, ReportSummaryOut
from app.services.llm import llm_service
from app.services.llm.service import LLMQuotaExhausted
from app.services.quant_research import report_text
from app.services.quant_research.moat.tenk import SEC_HEADERS
from app.services.quant_research.report import find_results_announcement, get_latest_report

CACHE_TTL = 60 * 24 * 3600
FAIL_TTL = 600
QUOTA_FAIL_TTL = 1800
LOCK_TTL = 600
LLM_TIMEOUT = 150
MAX_PDF_BYTES = 40 * 1024 * 1024

_tasks: set[asyncio.Task] = set()

# 要点里不能出现的买卖导向 / 承诺收益措辞（命中的条目直接丢弃）
_BANNED = ("建议买入", "建议卖出", "建议持有", "强烈推荐", "值得买", "值得买入", "稳赚", "必涨", "保证收益", "目标价", "买入评级",
           "strong buy", "buy rating", "we recommend", "price target")

_UNREADABLE = {"zh": "这份财报的 PDF 字体缺少字符映射（常见于部分港股公司的文件），文字提取不出来，没法整理要点，请直接看原文。",
               "en": "This PDF's fonts lack a character map (common for some Hong Kong filers), so its text cannot be extracted. Please read the original."}

NOTE = {
    "zh": "由 AI 根据财报原文关键章节整理，可能有遗漏或误差，一切以原文为准；不构成投资建议。",
    "en": "Summarized by AI from key sections of the report; it may miss or misstate details. The original report prevails. Not investment advice.",
}

_PROMPT = {
    "zh": """你是一名严谨的财经编辑。把下面上市公司财报的节选，整理成给「没学过财务的普通投资者」读的中文要点。

规则：
- 只依据所给文字，不要编造任何数字或结论；节选里没有的信息宁可不写。
- 数字保留原文口径，写明币种和单位（如「人民币 489.5 亿元」），同比 / 环比只写原文给出的。
- 不预测、不评价股价高低、不给任何买卖建议；管理层对未来的说法用「管理层表示……」转述。
- 专业术语第一次出现时用括号补一句大白话。
- 全部用简体中文输出（港股繁体原文也转成简体）。

输出：
- headline：一句话概括这期业绩（40 字以内）；
- key_numbers：最多 6 条关键数字（营收、净利润、每股收益、现金流、总资产等，原文有才写；change 写同比 / 环比）；
- highlights：4~6 条，这期发生了什么、变化来自哪里；
- watch_points：2~4 条，原文提到的风险、不确定性或需要留意的变化；
- outlook：管理层对后续的表述，没有就留空。""",
    "en": """You are a careful financial editor. Turn the excerpt of a listed company's report below into plain-language key points for a non-expert investor.

Rules:
- Use only the given text; never invent numbers or conclusions. If it is not in the excerpt, leave it out.
- Keep the original basis of every number, with currency and unit; give year-over-year / quarter-over-quarter changes only if stated.
- No predictions, no comments on whether the price is high or low, no buy/sell advice; report management's forward-looking statements as "Management said ...".
- Explain jargon in parentheses the first time it appears.
- Write everything in English.

Output: headline (one sentence, under 40 words); key_numbers (up to 6, only if present, with change); highlights (4-6 items: what happened and what drove it); watch_points (2-4 items: risks, uncertainties or changes the text mentions); outlook (management's stated outlook, empty if none).""",
}


def _key(lang: str, url: str, suffix: str = "") -> str:
    digest = hashlib.sha1(url.encode()).hexdigest()[:20]
    return f"quant_research:report_summary:v1:{lang}:{digest}{suffix}"


def sanitize(summary: ReportSummary) -> ReportSummary:
    """丢掉带买卖导向措辞的条目，限制条数与长度。"""
    def clean(items: list[str], limit: int) -> list[str]:
        out = [s.strip() for s in items if s and s.strip() and not any(b in s.lower() for b in _BANNED)]
        return [s[:300] for s in out][:limit]

    outlook = summary.outlook if not any(b in summary.outlook.lower() for b in _BANNED) else ""
    numbers = [n for n in summary.key_numbers if n.label and n.value][:6]
    return ReportSummary(headline=summary.headline.strip()[:120], key_numbers=numbers,
                         highlights=clean(summary.highlights, 6), watch_points=clean(summary.watch_points, 4),
                         outlook=outlook.strip()[:400])


async def _extract_text(report: LatestReportOut, market: str = "") -> str:
    """下载财报原文并挑出关键章节；文字不可读返回空串。港股报告 PDF 乱码时改用同期业绩公告（文件小、字体通常正常）。"""
    text = await _extract_from(report.url or "", report)
    if not text and market == "hk":
        alt = await find_results_announcement(report.symbol, report)
        if alt:
            logger.info("report_summary_hk_results_fallback", symbol=report.symbol)
            text = await _extract_from(alt, report)
    return text


async def _extract_from(url: str, report: LatestReportOut) -> str:
    """下载一个文件并挑关键章节（不可读返回空串）。"""
    assert url
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        if report.file_type == "html":
            resp = await client.get(url, headers=SEC_HEADERS)
            resp.raise_for_status()
            form = (report.title or "").split(" ")[-1]
            text = report_text.us_sections(report_text.html_to_text(resp.text), form)
        else:
            resp = await client.get(url)
            resp.raise_for_status()
            if len(resp.content) > MAX_PDF_BYTES:
                return ""
            pages = await asyncio.to_thread(report_text.pdf_pages, resp.content)
            text = report_text.pick_pdf_sections(pages)
    return text if report_text.looks_readable(text) else ""


async def summarize_text(text: str, report: LatestReportOut, lang: str) -> ReportSummary:
    """大模型整理要点（结构化输出）。"""
    human = (f"公司代码：{report.symbol}\n报告：{report.title or ''}（{report.report_type or ''}，披露日 {report.filed_date or ''}）\n\n"
             f"以下为财报节选：\n{text}")
    raw = await llm_service.call([SystemMessage(content=_PROMPT[lang]), HumanMessage(content=human)],
                                 response_format=ReportSummary, timeout=LLM_TIMEOUT)
    return sanitize(raw)


async def _generate(redis: Redis, report: LatestReportOut, lang: str, market: str = "") -> None:
    url = report.url or ""
    try:
        text = await _extract_text(report, market)
        if not text:
            await set_json(redis, _key(lang, url, ":fail"), {"reason": "unreadable"}, expire=24 * 3600)
            return
        summary = await summarize_text(text, report, lang)
        if not summary.headline:
            raise ValueError("empty summary")
        await set_json(redis, _key(lang, url), summary.model_dump(mode="json"), expire=CACHE_TTL)
        logger.info("report_summary_generated", symbol=report.symbol, chars=len(text))
    except LLMQuotaExhausted as e:
        await set_json(redis, _key(lang, url, ":fail"), {"reason": "quota"}, expire=QUOTA_FAIL_TTL)
        logger.warning("report_summary_quota_exhausted", symbol=report.symbol, error=str(e))
    except Exception as e:  # noqa: BLE001
        await set_json(redis, _key(lang, url, ":fail"), {"reason": "error"}, expire=FAIL_TTL)
        logger.warning("report_summary_failed", symbol=report.symbol, error=str(e))
    finally:
        await release_lock(redis, _key(lang, url, ":lock"))


def _out(report: LatestReportOut, lang: str, status: str, summary: ReportSummary | None = None,
         note: str | None = None) -> ReportSummaryOut:
    return ReportSummaryOut(status=status, symbol=report.symbol, report_type=report.report_type,  # type: ignore[arg-type]
                            filed_date=report.filed_date, summary=summary, note=note or (NOTE[lang] if summary else None))


async def get_report_summary(market: str, symbol: str, lang: str, *, redis: Redis | None,
                             kind: str = "latest", generate: bool = True) -> ReportSummaryOut:
    """缓存命中直接给；没有就（受每日上限约束）起一个后台生成，返回 generating。generate=False 只看缓存（App 打开阅读页时探一下，不触发生成）。"""
    if not settings.REPORT_SUMMARY_ENABLED:
        return ReportSummaryOut(status="disabled", symbol=symbol.upper())
    report = await get_latest_report(market, symbol, lang, redis=redis, kind=kind)
    if report.status != "ok" or not report.url:
        return ReportSummaryOut(status="unavailable", symbol=report.symbol)
    if redis is None:
        return _out(report, lang, "unavailable")

    cached = await get_json(redis, _key(lang, report.url))
    if cached:
        return _out(report, lang, "ready", ReportSummary(**cached))
    fail = await get_json(redis, _key(lang, report.url, ":fail"))
    if not generate:
        # 只看缓存：已知文字提不出来的，直接告诉 App（它就不显示「AI 总结」按钮了）
        if fail and fail.get("reason") == "unreadable":
            return _out(report, lang, "unreadable", note=_UNREADABLE[lang])
        return _out(report, lang, "not_generated")
    if fail:
        reasons = {"unreadable": _UNREADABLE,
                   "quota": {"zh": "今天的 AI 额度用完了，稍后再试。", "en": "AI quota is used up for now; try again later."}}
        note = reasons.get(fail.get("reason", ""), {"zh": "生成失败，稍后再试。", "en": "Generation failed; try again later."})[lang]
        status = "limit_reached" if fail.get("reason") == "quota" else "unreadable" if fail.get("reason") == "unreadable" else "unavailable"
        return _out(report, lang, status, note=note)

    if not await acquire_lock(redis, _key(lang, report.url, ":lock"), LOCK_TTL):
        return _out(report, lang, "generating")  # 别人（或上一次请求）已经在生成
    day = datetime.now(UTC).strftime("%Y%m%d")
    used = await incr_with_ttl(redis, f"quant_research:report_summary:daily:{day}", 2 * 24 * 3600)
    if used > settings.REPORT_SUMMARY_DAILY_LIMIT:
        await release_lock(redis, _key(lang, report.url, ":lock"))
        return _out(report, lang, "limit_reached",
                    note={"zh": "今天新生成的要点数量已到上限，明天再来。", "en": "The daily limit of new summaries was reached; try again tomorrow."}[lang])
    task = asyncio.create_task(_generate(redis, report, lang, market))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return _out(report, lang, "generating")
