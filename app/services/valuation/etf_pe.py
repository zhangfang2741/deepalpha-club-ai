"""各 ETF 历史 PE 数据服务。

数据策略：
  所有权益类 ETF 通过 ETF_SECTOR_MAP 映射到对应 GICS 行业，
  批量调用 FMP v4 /sector_price_earning_ratio 获取近 5 年 20 个季度 PE。

  关键优化：先一次性拉取所有季度的全行业快照（仅 20 次 API 调用），
  再按行业分配给各 ETF，避免 60×20=1200 次并发请求导致速率限制。

  注意：stable/sector-pe-snapshot 仅有约 4 季度历史，须使用 v4 端点。
  商品/债券/加密类 ETF（无行业映射）返回空序列。
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

_FMP_V4_BASE = "https://financialmodelingprep.com/api/v4"
_BATCH_SIZE = 10
_YEARS = 5  # 近 5 年数据

# 仅 SPDR 11 只一级板块 ETF 有行业 PE 映射，子板块 ETF 不显示 PE。
ETF_SECTOR_MAP: Dict[str, Set[str]] = {
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


# ── 核心：一次性拉取所有季度全行业 PE ────────────────────────────────────────

async def _fetch_sector_snapshot_on_date(client: httpx.AsyncClient, dt: str) -> List[dict]:
    """拉取指定日期的全行业 PE 快照。"""
    try:
        resp = await client.get(
            f"{_FMP_V4_BASE}/sector_price_earning_ratio",
            params={"date": dt, "exchange": "NYSE", "apikey": settings.FMP_API_KEY},
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else []
        logger.warning("sector_snapshot_failed", date=dt, status=resp.status_code)
    except Exception as e:
        logger.warning("sector_snapshot_failed", date=dt, error=str(e))
    return []


async def _fetch_all_sector_pe(
    client: httpx.AsyncClient, years: int = _YEARS
) -> Dict[str, Dict[str, float]]:
    """批量拉取近 years 年每季度末全行业 PE，返回 {date: {sector_name: pe}}。

    只需 20 次 API 调用（2 批 × 10 次），全部 ETF 共用此数据，
    避免 ETF 数量×季度数 = 1200+ 次重复请求触发速率限制。
    """
    dates = _quarter_end_dates(years=years)
    date_to_sectors: Dict[str, Dict[str, float]] = {}

    for i in range(0, len(dates), _BATCH_SIZE):
        batch = dates[i: i + _BATCH_SIZE]
        snapshots = await asyncio.gather(
            *[_fetch_sector_snapshot_on_date(client, dt) for dt in batch],
            return_exceptions=True,
        )
        for dt, recs in zip(batch, snapshots):
            if isinstance(recs, Exception) or not recs:
                continue
            sector_pe: Dict[str, float] = {}
            for rec in recs:
                sector_name = rec.get("sector", "")
                pe_raw = rec.get("pe")
                if not sector_name or pe_raw is None:
                    continue
                try:
                    pe_f = float(pe_raw)
                    if pe_f > 0:
                        sector_pe[sector_name] = round(pe_f, 2)
                except (TypeError, ValueError):
                    pass
            if sector_pe:
                date_to_sectors[dt] = sector_pe

    logger.info("sector_pe_fetched", dates_with_data=len(date_to_sectors), total_dates=len(dates))
    return date_to_sectors


def _extract_etf_pe_series(
    symbol: str,
    date_to_sectors: Dict[str, Dict[str, float]],
) -> List[Tuple[str, float]]:
    """从行业 PE 字典中提取 ETF 对应行业的历史 PE 序列（最新在前）。"""
    sector_names = ETF_SECTOR_MAP.get(symbol, set())
    if not sector_names:
        return []

    series: List[Tuple[str, float]] = []
    for dt, sector_map in date_to_sectors.items():
        for sn in sector_names:
            if sn in sector_map:
                series.append((dt, sector_map[sn]))
                break

    return sorted(series, key=lambda x: x[0], reverse=True)


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
    """获取所有 ETF 的 PE z-score 摘要。

    优化：一次性拉取所有季度全行业 PE（20 次 API 调用），
    再同步提取各 ETF 的行业 PE 序列，无并发速率限制风险。
    """
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

    async with httpx.AsyncClient() as client:
        date_to_sectors = await _fetch_all_sector_pe(client, years=_YEARS)

    etfs = [
        _build_summary_item(sym, sector_key, sector_cn, _extract_etf_pe_series(sym, date_to_sectors))
        for sym, sector_key, sector_cn in ordered
    ]
    with_data = sum(1 for e in etfs if e.z_score is not None)
    logger.info("etf_valuation_summary_done", total=len(etfs), with_data=with_data)
    return ETFValuationSummaryResponse(as_of=str(date.today()), etfs=etfs)


async def compute_etf_valuation_detail(symbol: str) -> ETFValuationDetail:
    """获取单个 ETF 完整的 PE 历史（用于详情图表）。"""
    sym = symbol.upper()

    async with httpx.AsyncClient() as client:
        date_to_sectors = await _fetch_all_sector_pe(client, years=_YEARS)

    pe_series = _extract_etf_pe_series(sym, date_to_sectors)

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
