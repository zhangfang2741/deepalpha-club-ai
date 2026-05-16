"""个 ETF 历史 PE 数据服务（FMP key-metrics 端点）。"""

import asyncio
import statistics
from datetime import date
from typing import Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.valuation import ETFValuationDetail, ETFValuationSummaryItem, ETFValuationSummaryResponse
from app.services.etf.constants import CHINESE_NAMES, ETF_LIBRARY

_FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"
_BATCH_SIZE = 10
_QUARTERS = 20  # 5 年季度数据


def compute_etf_z_score(pe_series: List[float], current_pe: float) -> Optional[float]:
    if len(pe_series) < 4:
        return None
    try:
        std = statistics.stdev(pe_series)
    except statistics.StatisticsError:
        return None
    if std == 0:
        return None
    return round((current_pe - statistics.mean(pe_series)) / std, 4)


def get_etf_label(z_score: Optional[float]) -> Tuple[str, str]:
    if z_score is None:
        return "数据不足", "insufficient"
    if z_score <= -2:
        return "极度低估", "extreme_undervalue"
    if z_score <= -1:
        return "低估", "undervalue"
    if z_score < 1:
        return "中性", "neutral"
    if z_score < 2:
        return "高估", "overvalue"
    return "极度高估", "extreme_overvalue"


async def _fetch_etf_pe_series(client: httpx.AsyncClient, symbol: str) -> List[Tuple[str, float]]:
    """获取单个 ETF 的历史季度 PE 序列（最新在前）。先试 key-metrics，再试 ratios。"""
    for endpoint, pe_field in (
        ("key-metrics", "peRatio"),
        ("ratios", "priceEarningsRatio"),
    ):
        try:
            resp = await client.get(
                f"{_FMP_STABLE_BASE}/{endpoint}",
                params={
                    "symbol": symbol,
                    "limit": _QUARTERS,
                    "period": "quarter",
                    "apikey": settings.FMP_API_KEY,
                },
                timeout=20,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            if not isinstance(data, list):
                continue
            series: List[Tuple[str, float]] = []
            for rec in data:
                dt = rec.get("date") or rec.get("Date")
                raw = rec.get(pe_field)
                if not dt or raw is None:
                    continue
                try:
                    pe = float(raw)
                except (TypeError, ValueError):
                    continue
                if pe > 0:
                    series.append((dt, round(pe, 2)))
            if series:
                return series
        except Exception as e:
            logger.warning("etf_pe_fetch_failed", symbol=symbol, endpoint=endpoint, error=str(e))
    return []


def _build_summary_item(
    symbol: str,
    sector_key: str,
    sector_cn: str,
    pe_series: List[Tuple[str, float]],
) -> ETFValuationSummaryItem:
    if pe_series:
        current_pe = pe_series[0][1]
        all_pes = [pe for _, pe in pe_series]
        z = compute_etf_z_score(all_pes, current_pe)
        hist_mean = round(statistics.mean(all_pes), 4) if len(all_pes) >= 2 else None
        hist_std = round(statistics.stdev(all_pes), 4) if len(all_pes) >= 2 else None
    else:
        current_pe = None
        z = None
        hist_mean = None
        hist_std = None

    label, label_en = get_etf_label(z)
    return ETFValuationSummaryItem(
        symbol=symbol,
        name=CHINESE_NAMES.get(symbol, symbol),
        sector_key=sector_key,
        sector_cn=sector_cn,
        current_pe=current_pe,
        hist_mean=hist_mean,
        hist_std=hist_std,
        z_score=z,
        label=label,
        label_en=label_en,
        data_quarters=len(pe_series),
    )


async def compute_etf_valuation_summary() -> ETFValuationSummaryResponse:
    """并发拉取所有 ETF 的季度 PE，计算 z-score 摘要（4h 缓存）。"""
    if not settings.FMP_API_KEY:
        logger.warning("etf_valuation_no_api_key")
        return ETFValuationSummaryResponse(as_of=str(date.today()), etfs=[])

    # 去重并记录每个 ETF 所属板块（取首次出现的板块）
    ordered: List[Tuple[str, str, str]] = []
    seen: set = set()
    for sector_key, symbols in ETF_LIBRARY.items():
        sector_cn = sector_key[3:]  # "01 信息技术" → "信息技术"
        for sym in symbols:
            if sym not in seen:
                seen.add(sym)
                ordered.append((sym, sector_key, sector_cn))

    logger.info("etf_valuation_summary_start", total_etfs=len(ordered))

    pe_map: Dict[str, List[Tuple[str, float]]] = {}
    async with httpx.AsyncClient() as client:
        for i in range(0, len(ordered), _BATCH_SIZE):
            batch = ordered[i : i + _BATCH_SIZE]
            results = await asyncio.gather(
                *[_fetch_etf_pe_series(client, sym) for sym, _, _ in batch],
                return_exceptions=True,
            )
            for (sym, _, _), res in zip(batch, results):
                pe_map[sym] = res if not isinstance(res, Exception) else []

    etfs = [
        _build_summary_item(sym, sector_key, sector_cn, pe_map.get(sym, []))
        for sym, sector_key, sector_cn in ordered
    ]
    with_data = sum(1 for e in etfs if e.z_score is not None)
    logger.info("etf_valuation_summary_done", total=len(etfs), with_data=with_data)
    return ETFValuationSummaryResponse(as_of=str(date.today()), etfs=etfs)


async def compute_etf_valuation_detail(symbol: str) -> ETFValuationDetail:
    """获取单个 ETF 完整的 PE 历史（用于详情图表）。"""
    sym = symbol.upper()
    async with httpx.AsyncClient() as client:
        pe_series = await _fetch_etf_pe_series(client, sym)

    if pe_series:
        current_pe = pe_series[0][1]
        all_pes = [pe for _, pe in pe_series]
        z = compute_etf_z_score(all_pes, current_pe)
        hist_mean = round(statistics.mean(all_pes), 4) if len(all_pes) >= 2 else None
        hist_std = round(statistics.stdev(all_pes), 4) if len(all_pes) >= 2 else None
    else:
        current_pe = None
        z = None
        hist_mean = None
        hist_std = None

    label, label_en = get_etf_label(z)
    # hist_pe 按日期升序返回（前端图表用）
    hist_pe_asc = [{"date": d, "pe": pe} for d, pe in reversed(pe_series)]

    return ETFValuationDetail(
        symbol=sym,
        name=CHINESE_NAMES.get(sym, sym),
        current_pe=current_pe,
        hist_mean=hist_mean,
        hist_std=hist_std,
        z_score=z,
        label=label,
        label_en=label_en,
        hist_pe=hist_pe_asc,
        data_quarters=len(pe_series),
    )
