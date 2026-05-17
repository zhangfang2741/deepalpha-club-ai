"""个 ETF 历史 PE 数据服务。

数据策略：
  SPDR 板块 ETF（XLK/XLV/XLF 等 11 只）：直接复用
    FMP stable /sector-pe-snapshot 的行业 PE，与行业估值保持一致。
  其余 ETF：依次尝试 key-metrics → ratios（含/不含 period 参数）。
  商品/债券/加密类 ETF 通常无 PE，返回空序列。
"""

import asyncio
import statistics
from datetime import date
from typing import Dict, List, Optional, Set, Tuple

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.valuation import ETFValuationDetail, ETFValuationSummaryItem, ETFValuationSummaryResponse
from app.services.etf.constants import CHINESE_NAMES, ETF_LIBRARY
from app.services.valuation.sector_pe import _quarter_end_dates

_FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"
_BATCH_SIZE = 10
_QUARTERS = 20  # 5 年季度数据

# SPDR 板块 ETF → FMP sector-pe-snapshot 中对应的行业名称（可能有多个别名）
SPDR_ETF_SECTOR: Dict[str, Set[str]] = {
    "XLK":  {"Technology"},
    "XLV":  {"Healthcare", "Health Care"},
    "XLF":  {"Financial Services", "Financials"},
    "XLY":  {"Consumer Cyclical", "Consumer Discretionary"},
    "XLC":  {"Communication Services"},
    "XLI":  {"Industrials"},
    "XLP":  {"Consumer Defensive", "Consumer Staples"},
    "XLE":  {"Energy"},
    "XLU":  {"Utilities"},
    "XLRE": {"Real Estate"},
    "XLB":  {"Basic Materials", "Materials"},
}


# ── 辅助：z-score / 标签 ──────────────────────────────────────────────────────

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


# ── SPDR 板块 ETF：复用 sector-pe-snapshot ───────────────────────────────────

async def _fetch_sector_snapshot_on_date(client: httpx.AsyncClient, dt: str) -> List[dict]:
    """拉取指定日期的全行业 PE 快照。"""
    try:
        resp = await client.get(
            f"{_FMP_STABLE_BASE}/sector-pe-snapshot",
            params={"date": dt, "exchange": "NYSE", "apikey": settings.FMP_API_KEY},
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("spdr_sector_snapshot_failed", date=dt, error=str(e))
    return []


async def _fetch_spdr_pe_series(client: httpx.AsyncClient, symbol: str) -> List[Tuple[str, float]]:
    """SPDR 板块 ETF 使用行业 PE 数据（近 5 年 20 季度）。"""
    sector_names = SPDR_ETF_SECTOR.get(symbol, set())
    if not sector_names:
        return []

    dates = _quarter_end_dates(years=5)  # 20 个季度
    results: List[Tuple[str, float]] = []

    for i in range(0, len(dates), _BATCH_SIZE):
        batch = dates[i: i + _BATCH_SIZE]
        snapshots = await asyncio.gather(
            *[_fetch_sector_snapshot_on_date(client, dt) for dt in batch],
            return_exceptions=True,
        )
        for dt, recs in zip(batch, snapshots):
            if isinstance(recs, Exception) or not recs:
                continue
            for rec in recs:
                if rec.get("sector") in sector_names:
                    pe = rec.get("pe")
                    try:
                        pe_f = float(pe)
                    except (TypeError, ValueError):
                        continue
                    if pe_f > 0:
                        results.append((dt, round(pe_f, 2)))
                    break  # 每个日期只取一条匹配记录

    # 去重 + 按日期降序（最新在前）
    seen: Set[str] = set()
    deduped: List[Tuple[str, float]] = []
    for dt, pe in sorted(results, key=lambda x: x[0], reverse=True):
        if dt not in seen:
            seen.add(dt)
            deduped.append((dt, pe))
    return deduped


# ── 非 SPDR ETF：尝试多个 FMP 端点 ──────────────────────────────────────────

async def _fetch_equity_etf_pe_series(client: httpx.AsyncClient, symbol: str) -> List[Tuple[str, float]]:
    """
    对权益类 ETF 尝试 4 种 FMP 端点组合获取历史 PE。
    对商品/债券/加密类 ETF 通常返回空列表。
    """
    attempts = [
        ("key-metrics", "peRatio",              {"period": "quarter", "limit": _QUARTERS}),
        ("key-metrics", "peRatio",              {"limit": _QUARTERS}),
        ("ratios",      "priceEarningsRatio",   {"period": "quarter", "limit": _QUARTERS}),
        ("ratios",      "priceEarningsRatio",   {"limit": _QUARTERS}),
    ]
    for endpoint, pe_field, extra_params in attempts:
        try:
            params = {"symbol": symbol, "apikey": settings.FMP_API_KEY, **extra_params}
            resp = await client.get(f"{_FMP_STABLE_BASE}/{endpoint}", params=params, timeout=20)
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
                logger.info("equity_etf_pe_found", symbol=symbol, endpoint=endpoint, points=len(series))
                return series
        except Exception as e:
            logger.warning("equity_etf_pe_attempt_failed", symbol=symbol, endpoint=endpoint, error=str(e))
    return []


# ── 统一入口 ──────────────────────────────────────────────────────────────────

async def _fetch_etf_pe_series(client: httpx.AsyncClient, symbol: str) -> List[Tuple[str, float]]:
    """获取 ETF 历史季度 PE 序列（最新在前）。"""
    if symbol in SPDR_ETF_SECTOR:
        series = await _fetch_spdr_pe_series(client, symbol)
        if series:
            return series
        # sector-pe-snapshot 失败时回退到 equity 路径
    return await _fetch_equity_etf_pe_series(client, symbol)


# ── 摘要 / 详情构建 ───────────────────────────────────────────────────────────

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

    ordered: List[Tuple[str, str, str]] = []
    seen: Set[str] = set()
    for sector_key, symbols in ETF_LIBRARY.items():
        sector_cn = sector_key[3:]
        for sym in symbols:
            if sym not in seen:
                seen.add(sym)
                ordered.append((sym, sector_key, sector_cn))

    logger.info("etf_valuation_summary_start", total_etfs=len(ordered))

    pe_map: Dict[str, List[Tuple[str, float]]] = {}
    async with httpx.AsyncClient() as client:
        for i in range(0, len(ordered), _BATCH_SIZE):
            batch = ordered[i: i + _BATCH_SIZE]
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
