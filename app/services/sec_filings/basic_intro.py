"""公司基础介绍服务：中英文对照。

英文简介与基础字段直接取自 FMP company profile（真实数据，不是 LLM 生成）；中文
简介是对该英文简介的 LLM 翻译。之所以不接第三方翻译 API：项目里没有 Google Cloud
Translation 的 key/依赖，现接需要先去 GCP 开通、拿凭证；而 LLM（GOOGLE_API_KEY /
OPENAI_API_KEY / ANTHROPIC_API_KEY）本来就已配置好，`llm_service` 现成可用，一段
几百字的公司简介单次调用即可翻完，不比调 Google 翻译慢，零新增配置就能今天上线。
翻译 prompt 与口径复用 app/services/transcript_ai.py 的财经翻译方案。
"""

from __future__ import annotations

import json
from typing import Any, Optional, cast

from langchain_core.messages import HumanMessage, SystemMessage
from redis.asyncio import Redis

from app.core.logging import logger
from app.services.analyzer.fmp_client import fmp_client
from app.services.llm import llm_service
from app.utils.market import InvalidSymbolError, fmp_symbol

_CACHE_PREFIX = "sec:basic_intro:v1"
_CACHE_TTL = 604800  # 7 天：公司基础介绍变动很慢，与 company_profile 的缓存周期对齐

_TRANSLATE_SYSTEM_PROMPT = """你是一名专业的金融财经翻译，负责把英文上市公司简介翻译成简体中文。

要求：
- 严格忠实原文，不增删、不总结、不解释、不编造。
- 使用金融/财经行业的规范中文术语。
- 公司名、产品名、人名保持英文原文，其余译成中文。
- 只输出翻译后的中文正文，不要添加任何前言、注释或说明。"""


def _contains_cjk(text: str) -> bool:
    """文本是否含有中日韩汉字（判断译文是否真的是中文）。"""
    return any("一" <= ch <= "鿿" for ch in text)


def _extract_message_text(content: object) -> str:
    """从 LLM 响应中只提取正文文本，丢弃 Claude extended thinking 等推理块。

    与 app/services/transcript_ai.py 的同名函数逻辑一致，这里保持独立小实现，
    不跨模块 import 私有函数。
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") in {"thinking", "reasoning", "redacted_thinking"}:
                    continue
                text = block.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content).strip()


def _cache_key(ticker: str) -> str:
    return f"{_CACHE_PREFIX}:{ticker.upper()}"


async def _translate(description_en: str) -> str:
    """把英文简介翻译成中文；LLM 异常或译文不含中文（模型回显原文）时返回空字符串。

    返回空不阻塞主流程——英文数据本身仍照常返回，只是中文栏位留空，前端回退显示英文。
    """
    if not description_en.strip():
        return ""
    try:
        response = await llm_service.call(
            [
                SystemMessage(content=_TRANSLATE_SYSTEM_PROMPT),
                HumanMessage(content=description_en),
            ],
            temperature=0.2,
        )
    except Exception as e:
        logger.warning("company_basic_intro_translate_failed", error=str(e))
        return ""

    text = _extract_message_text(response.content)
    if not _contains_cjk(text):
        logger.warning("company_basic_intro_translate_not_chinese")
        return ""
    return text


async def get_basic_intro(symbol: str, redis: Optional[Redis] = None) -> Optional[dict]:
    """按股票代码取公司基础介绍：FMP 英文原文 + LLM 中文翻译，按 FMP 代码缓存 7 天。

    Args:
        symbol: 股票代码，接受任意市场惯用写法（AAPL / 0700 / 0700.HK / 600519 等），
            内部统一转换成 FMP 要的代码形态。
        redis: 可选缓存客户端。

    Returns:
        dict（与 CompanyBasicIntroResponse 对齐）或 None（代码无法识别 / FMP 无该标的数据）。
    """
    try:
        ticker = fmp_symbol(symbol)
    except InvalidSymbolError:
        logger.warning("company_basic_intro_invalid_symbol", symbol=symbol)
        return None

    cache_key = _cache_key(ticker)
    if redis is not None:
        try:
            raw = await redis.get(cache_key)
            if raw:
                logger.info("company_basic_intro_cache_hit", ticker=ticker)
                return json.loads(raw)
        except Exception as e:
            logger.warning("company_basic_intro_cache_read_error", ticker=ticker, error=str(e))

    # FmpClient.get_company_profile 的类型标注是 Dict[str, Any]，但 /profile 端点
    # 实际返回的是 JSON 数组（单元素列表）；用 cast 如实描述运行时形状，而不是让
    # pyright 按错误的声明类型把 rows[0] 当成用整数下标查字典报错。
    rows = cast("list[dict[str, Any]]", await fmp_client.get_company_profile(ticker))
    row = rows[0] if isinstance(rows, list) and rows else None
    if not row:
        logger.warning("company_basic_intro_profile_not_found", ticker=ticker)
        return None

    description_en = str(row.get("description") or "")
    description_zh = await _translate(description_en)

    result = {
        "ticker": str(row.get("symbol") or ticker),
        "name": str(row.get("companyName") or ""),
        "industry": str(row.get("industry") or ""),
        "sector": str(row.get("sector") or ""),
        "ceo": str(row.get("ceo") or ""),
        "website": str(row.get("website") or ""),
        "employees": str(row.get("fullTimeEmployees") or ""),
        "ipo_date": str(row.get("ipoDate") or ""),
        "description_en": description_en,
        "description_zh": description_zh,
    }

    # 翻译失败（description_zh 为空）时不缓存：避免把这次的空译文缓存 7 天，
    # 下次请求还能重新尝试翻译；英文数据本身此时仍正常返回给用户。
    if redis is not None and description_zh:
        try:
            await redis.set(cache_key, json.dumps(result, ensure_ascii=False), ex=_CACHE_TTL)
        except Exception as e:
            logger.warning("company_basic_intro_cache_write_error", ticker=ticker, error=str(e))

    logger.info("company_basic_intro_generated", ticker=ticker, translated=bool(description_zh))
    return result
