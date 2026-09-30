"""量化评级股票池：标普 500 与纳斯达克 100 的并集及行业映射。

两套成分均取自维基百科成分表，按代码去重后 Redis 缓存 7 天。纳斯达克 100 使用 ICB
Industry 映射到项目统一的 GICS 板块键，保证行业分布与标普 500 成分使用同一套口径。
"""

from __future__ import annotations

import asyncio
import io
import json
import re

import httpx
import pandas as pd
from redis.asyncio import Redis

from app.core.logging import logger

WIKI_PAGES = {
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "nasdaq100": "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies",
}
_UA = "Mozilla/5.0 (compatible; DeepAlphaQuant/1.0; +https://deepalpha.club)"
CACHE_KEY = "quant:universe:sp500_nasdaq100:v1"
CACHE_TTL = 7 * 86400
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z\-]{0,6}$")

# GICS 板块键 → (维基英文名, 中文名, 英文展示名)
GICS_SECTORS: dict[str, tuple[str, str, str]] = {
    "communication_services": ("Communication Services", "通信服务", "Communication Services"),
    "consumer_discretionary": ("Consumer Discretionary", "可选消费", "Consumer Discretionary"),
    "consumer_staples": ("Consumer Staples", "必需消费", "Consumer Staples"),
    "energy": ("Energy", "能源", "Energy"),
    "financials": ("Financials", "金融", "Financials"),
    "health_care": ("Health Care", "医疗保健", "Health Care"),
    "industrials": ("Industrials", "工业", "Industrials"),
    "information_technology": ("Information Technology", "信息技术", "Information Technology"),
    "materials": ("Materials", "原材料", "Materials"),
    "real_estate": ("Real Estate", "房地产", "Real Estate"),
    "utilities": ("Utilities", "公用事业", "Utilities"),
}
_WIKI_TO_KEY = {v[0]: k for k, v in GICS_SECTORS.items()}

_NASDAQ_INDUSTRY_TO_GICS = {
    "Technology": "information_technology",
    "Consumer Discretionary": "consumer_discretionary",
    "Industrials": "industrials",
    "Health Care": "health_care",
    "Consumer Staples": "consumer_staples",
    "Utilities": "utilities",
    "Telecommunications": "communication_services",
    "Energy": "energy",
    "Basic Materials": "materials",
    "Financials": "financials",
}

FMP_SECTOR_TO_GICS: dict[str, str] = {
    "Technology": "information_technology",
    "Healthcare": "health_care",
    "Financial Services": "financials",
    "Consumer Cyclical": "consumer_discretionary",
    "Consumer Defensive": "consumer_staples",
    "Basic Materials": "materials",
    "Communication Services": "communication_services",
    "Energy": "energy",
    "Industrials": "industrials",
    "Real Estate": "real_estate",
    "Utilities": "utilities",
}


def normalize_us_symbol(symbol: str) -> str:
    """美股代码规范化：大写，类别股的点号换成连字符（BRK.B → BRK-B，与成分表、FMP 一致）。"""
    return symbol.strip().upper().replace(".", "-")


def sector_name(key: str, lang: str) -> str:
    """GICS 板块展示名。"""
    _, zh, en = GICS_SECTORS[key]
    return zh if lang == "zh" else en


def parse_sp_table(html: str) -> list[tuple[str, str, str]]:
    """解析维基成分表 → [(symbol, name, sector_key)]。代码 . 换成 -，丢弃异常代码。"""
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        return []
    for tbl in tables:
        cols = [str(c) for c in tbl.columns]
        if "Symbol" in cols and "GICS Sector" in cols:
            out = []
            for sym, name, sector in zip(tbl["Symbol"], tbl["Security"], tbl["GICS Sector"], strict=False):
                s = str(sym).strip().replace(".", "-")
                key = _WIKI_TO_KEY.get(str(sector).strip())
                if key and _SYMBOL_RE.match(s):
                    out.append((s, str(name).strip(), key))
            return out
    return []


def parse_nasdaq100_table(html: str) -> list[tuple[str, str, str]]:
    """解析纳斯达克 100 成分表（Ticker / Company / ICB Industry）并映射行业。"""
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        return []
    for tbl in tables:
        cols = [str(c) for c in tbl.columns]
        industry_col = next((c for c in cols if c.startswith("ICB Industry")), None)
        if "Ticker" not in cols or "Company" not in cols or industry_col is None:
            continue
        out = []
        for sym, name, industry in zip(tbl["Ticker"], tbl["Company"], tbl[industry_col], strict=False):
            symbol = str(sym).strip().replace(".", "-")
            sector = _NASDAQ_INDUSTRY_TO_GICS.get(str(industry).strip())
            if sector and _SYMBOL_RE.match(symbol):
                out.append((symbol, str(name).strip(), sector))
        return out
    return []


async def fetch_target_universe(redis: Redis | None) -> dict[str, tuple[str, str]]:
    """返回标普 500 与纳斯达克 100 并集。"""
    if redis is not None:
        try:
            raw = await redis.get(CACHE_KEY)
            if raw:
                return {k: tuple(v) for k, v in json.loads(raw).items()}  # type: ignore[misc]
        except Exception as e:  # noqa: BLE001
            logger.warning("quant_universe_cache_read_failed", error=str(e))
    out: dict[str, tuple[str, str]] = {}
    complete = True
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": _UA}, follow_redirects=True) as c:
        for index, url in WIKI_PAGES.items():
            try:
                resp = await c.get(url)
                parser = parse_sp_table if index == "sp500" else parse_nasdaq100_table
                rows = await asyncio.to_thread(parser, resp.text) if resp.status_code == 200 else []
            except Exception as e:  # noqa: BLE001
                logger.warning("quant_universe_fetch_failed", index=index, error=str(e))
                rows = []
            minimum = 450 if index == "sp500" else 90
            if len(rows) < minimum:
                complete = False
                logger.warning("quant_universe_page_incomplete", index=index, count=len(rows))
            for sym, name, key in rows:
                out.setdefault(sym, (name, key))
    logger.info("quant_universe_fetched", count=len(out), complete=complete)
    if complete and redis is not None:
        try:
            await redis.set(CACHE_KEY, json.dumps(out), ex=CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("quant_universe_cache_write_failed", error=str(e))
    return out


async def fetch_sp1500(redis: Redis | None) -> dict[str, tuple[str, str]]:
    """兼容旧调用方；新的批处理入口使用 fetch_target_universe。"""
    return await fetch_target_universe(redis)
