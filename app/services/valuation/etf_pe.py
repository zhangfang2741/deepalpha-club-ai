"""个 ETF 历史 PE 数据服务。

数据策略：
  权益类 ETF：通过 ETF_SECTOR_MAP 映射到 FMP sector-pe-snapshot 行业 PE，
    按季度批量拉取近 5 年共 20 个数据点，保证历史深度一致。
  商品/债券/加密类 ETF（无映射）：返回空序列。
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

# 所有权益类 ETF → FMP sector-pe-snapshot 中对应的行业名称
# 子板块 ETF 使用其最近的父 GICS 行业 PE（近似值，但保证 5 年历史深度）
ETF_SECTOR_MAP: Dict[str, Set[str]] = {
    # ── SPDR 11 只标准板块 ETF ──
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
    # ── 信息技术子板块 ──
    "SOXX": {"Technology"},   # 半导体
    "IGV":  {"Technology"},   # 软件
    "AIQ":  {"Technology"},   # 人工智能
    "SKYY": {"Technology"},   # 云计算
    "QTUM": {"Technology"},   # 量子计算
    "BUG":  {"Technology"},   # 网络安全
    "BLOK": {"Technology"},   # 区块链
    "PNQI": {"Technology"},   # 纳斯达克互联网
    "QQQ":  {"Technology"},   # 纳斯达克100
    "ARKK": {"Technology"},   # ARK 创新
    # ── 医疗保健子板块 ──
    "XHE":  {"Healthcare", "Health Care"},  # 医疗设备
    "IHF":  {"Healthcare", "Health Care"},  # 医疗保险
    "XBI":  {"Healthcare", "Health Care"},  # 生物科技
    "PJP":  {"Healthcare", "Health Care"},  # 制药
    # ── 金融子板块 ──
    "KBE":  {"Financial Services", "Financials"},  # 银行
    "IYG":  {"Financial Services", "Financials"},  # 金融服务
    "KIE":  {"Financial Services", "Financials"},  # 保险
    "KCE":  {"Financial Services", "Financials"},  # 资本市场
    "REM":  {"Real Estate"},                        # 抵押 REIT
    # ── 可选消费子板块 ──
    "CARZ": {"Consumer Cyclical", "Consumer Discretionary"},  # 汽车
    "XRT":  {"Consumer Cyclical", "Consumer Discretionary"},  # 零售
    "XHB":  {"Consumer Cyclical", "Consumer Discretionary"},  # 家居建设
    "PEJ":  {"Consumer Cyclical", "Consumer Discretionary"},  # 休闲娱乐
    "PKB":  {"Consumer Cyclical", "Consumer Discretionary"},  # 住宅建设
    # ── 必需消费子板块 ──
    "PBJ":  {"Consumer Defensive", "Consumer Staples"},  # 食品饮料
    "MOO":  {"Consumer Defensive", "Consumer Staples"},  # 农业
    # ── 工业子板块 ──
    "ITA":  {"Industrials"},   # 航空航天防务
    "PAVE": {"Industrials"},   # 基础设施
    "IYT":  {"Industrials"},   # 交通运输
    "JETS": {"Industrials"},   # 航空
    "BOAT": {"Industrials"},   # 航运
    "IFRA": {"Industrials"},   # 基础设施
    "UFO":  {"Industrials"},   # 太空
    "SHLD": {"Industrials"},   # 国防
    # ── 能源子板块 ──
    "IEZ":  {"Energy"},        # 油气设备服务
    "XOP":  {"Energy"},        # 油气勘探
    "FAN":  {"Utilities"},     # 风能
    "TAN":  {"Utilities"},     # 太阳能
    "NLR":  {"Utilities"},     # 核能
    # ── 原材料子板块 ──
    "XME":  {"Basic Materials", "Materials"},   # 金属采矿
    "WOOD": {"Basic Materials", "Materials"},   # 林业
    "COPX": {"Basic Materials", "Materials"},   # 铜矿
    "SLX":  {"Basic Materials", "Materials"},   # 钢铁
    "BATT": {"Basic Materials", "Materials"},   # 锂电池
    # ── 通信服务子板块 ──
    "IYZ":  {"Communication Services"},         # 电信
    # ── 房地产子板块 ──
    "INDS": {"Real Estate"},   # 工业地产
    "REZ":  {"Real Estate"},   # 住宅 REIT
    "SRVR": {"Real Estate"},   # 数据中心 REIT
    # ── 公用事业子板块 ──
    "ICLN": {"Utilities"},     # 清洁能源
    "PHO":  {"Utilities"},     # 水资源
    "GRID": {"Utilities"},     # 智能电网
    # 无法映射（商品/债券/加密/国际宽基）：
    #   GLD GLTR SLV TLT EEM VEA FXI BITO GBTC ETHE MSOS IPO SPY
    #   → 返回空序列
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


# ── sector-pe-snapshot 批量拉取 ───────────────────────────────────────────────

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
        logger.warning("sector_snapshot_failed", date=dt, error=str(e))
    return []


async def _fetch_sector_mapped_pe_series(
    client: httpx.AsyncClient, symbol: str
) -> List[Tuple[str, float]]:
    """使用 sector-pe-snapshot 获取 ETF 历史 PE（近 5 年 20 季度）。"""
    sector_names = ETF_SECTOR_MAP.get(symbol, set())
    if not sector_names:
        return []

    dates = _quarter_end_dates(years=5)
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
                    break

    # 去重 + 按日期降序（最新在前）
    seen: Set[str] = set()
    deduped: List[Tuple[str, float]] = []
    for dt, pe in sorted(results, key=lambda x: x[0], reverse=True):
        if dt not in seen:
            seen.add(dt)
            deduped.append((dt, pe))
    return deduped


async def _fetch_etf_pe_series(client: httpx.AsyncClient, symbol: str) -> List[Tuple[str, float]]:
    """获取 ETF 历史季度 PE 序列（最新在前）。

    映射到行业的 ETF → sector-pe-snapshot（保证近 5 年数据）
    未映射 ETF（商品/债券/加密等） → 返回空序列
    """
    return await _fetch_sector_mapped_pe_series(client, symbol)


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
