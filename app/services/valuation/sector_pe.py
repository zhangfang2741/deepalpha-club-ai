"""行业估值 z-score 计算服务（FMP 直接行业 PE 数据）。

数据源：FMP v4 /sector_price_earning_ratio?date=YYYY-MM-DD
  每次请求返回当日所有 GICS 行业的 PE 比率。
  批量拉取近 10 年每季度末日期（40 次并发请求），聚合构建历史序列。

算法：
  对每个行业：
    hist_pe  = 过去 40 个季度的 PE 序列
    z_score  = (current_pe - mean(hist_pe)) / stdev(hist_pe)

  z ≤ -2  → 极度低估
  -2 < z ≤ -1 → 低估
  -1 < z < 1  → 中性
  1 ≤ z < 2  → 高估
  z ≥ 2   → 极度高估
"""

import asyncio
import statistics
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.valuation import SectorValuation, SectorValuationResponse

_FMP_V4_BASE = "https://financialmodelingprep.com/api/v4"

# FMP 返回的行业名 → 中文映射
SECTOR_CN_MAP: Dict[str, str] = {
    "Technology": "信息技术",
    "Healthcare": "医疗保健",
    "Health Care": "医疗保健",
    "Financial Services": "金融",
    "Financials": "金融",
    "Consumer Cyclical": "可选消费",
    "Consumer Discretionary": "可选消费",
    "Communication Services": "通信服务",
    "Industrials": "工业",
    "Consumer Defensive": "必需消费",
    "Consumer Staples": "必需消费",
    "Energy": "能源",
    "Utilities": "公用事业",
    "Real Estate": "房地产",
    "Basic Materials": "原材料",
    "Materials": "原材料",
}

# 每批并发请求数量，避免超出 FMP 速率限制
_BATCH_SIZE = 10


def _quarter_end_dates(years: int = 10) -> List[str]:
    """生成过去 `years` 年的季度末日期列表（最新在前）。"""
    today = date.today()
    dates: List[str] = []
    for year in range(today.year, today.year - years - 1, -1):
        for month, day in ((12, 31), (9, 30), (6, 30), (3, 31)):
            d = date(year, month, day)
            if d < today:
                dates.append(d.strftime("%Y-%m-%d"))
    return dates[:40]  # 取最近 40 个季度


def _pe_value(raw: float | None) -> Optional[float]:
    """过滤无效 PE（None、零、负值）。"""
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def compute_z_score(values: List[float], current: float) -> Optional[float]:
    """计算当前值的 z-score（样本标准差）。"""
    if len(values) < 2:
        return None
    try:
        std = statistics.stdev(values)
    except statistics.StatisticsError:
        return None
    if std == 0:
        return None
    return round((current - statistics.mean(values)) / std, 4)


def get_valuation_label(z_score: Optional[float]) -> Tuple[str, str]:
    """将 z-score 映射为（中文标签，英文键）。"""
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


def _pe_from_record(record: dict) -> Optional[float]:
    """从单条 FMP 行业 PE 记录中提取 PE 值。"""
    return _pe_value(record.get("pe") or record.get("peRatio"))


def build_sector_valuation(
    sector: str,
    sector_cn: str,
    pe_series: List[Tuple[str, float]],  # [(date, pe), ...] 降序
) -> SectorValuation:
    """根据历史 PE 序列构建 SectorValuation（pe_series 最新在前）。"""
    current_pe = pe_series[0][1] if pe_series else None
    all_pes = [pe for _, pe in pe_series]

    hist_mean: Optional[float] = None
    hist_std: Optional[float] = None
    z_score: Optional[float] = None

    if len(all_pes) >= 2 and current_pe is not None:
        hist_mean = round(statistics.mean(all_pes), 4)
        hist_std = round(statistics.stdev(all_pes), 4)
        z_score = compute_z_score(all_pes, current_pe)

    label, label_en = get_valuation_label(z_score)

    hist_pe_asc = [{"date": d, "pe": pe} for d, pe in reversed(pe_series)]
    as_of_date = pe_series[0][0] if pe_series else ""

    return SectorValuation(
        sector=sector,
        sector_cn=sector_cn,
        etf_symbol="",
        current_pe=current_pe,
        hist_mean=hist_mean,
        hist_std=hist_std,
        z_score=z_score,
        label=label,
        label_en=label_en,
        hist_pe=hist_pe_asc,
        data_quarters=len(pe_series),
    )


async def _fetch_date_sector_pe(client: httpx.AsyncClient, dt: str) -> List[dict]:
    """拉取单个日期的行业 PE 数据。"""
    try:
        resp = await client.get(
            f"{_FMP_V4_BASE}/sector_price_earning_ratio",
            params={"date": dt, "exchange": "NYSE", "apikey": settings.FMP_API_KEY},
            timeout=20,
        )
        if resp.status_code == 401:
            logger.warning("fmp_sector_pe_unauthorized", date=dt)
            return []
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        logger.warning("fmp_sector_pe_fetch_failed", date=dt, error=str(e))
        return []


async def compute_sector_valuations() -> SectorValuationResponse:
    """并发拉取 40 个季度的行业 PE，聚合后计算 z-score。"""
    dates = _quarter_end_dates(years=10)
    logger.info("sector_valuation_compute_start", quarters=len(dates))

    # 按批次并发拉取，每批 _BATCH_SIZE 个日期
    all_records: List[Tuple[str, List[dict]]] = []
    async with httpx.AsyncClient() as client:
        for i in range(0, len(dates), _BATCH_SIZE):
            batch = dates[i: i + _BATCH_SIZE]
            results = await asyncio.gather(
                *[_fetch_date_sector_pe(client, dt) for dt in batch],
                return_exceptions=True,
            )
            for dt, res in zip(batch, results):
                if isinstance(res, Exception):
                    logger.warning("sector_pe_batch_error", date=dt, error=str(res))
                    all_records.append((dt, []))
                else:
                    all_records.append((dt, res))

    # 按行业聚合 → {sector: [(date, pe), ...]} 降序
    sector_pe_map: Dict[str, List[Tuple[str, float]]] = {}
    for dt, records in all_records:
        for rec in records:
            sector_name = rec.get("sector", "")
            pe = _pe_from_record(rec)
            if not sector_name or pe is None:
                continue
            sector_pe_map.setdefault(sector_name, []).append((dt, pe))

    # 保证每个行业序列有序（降序），去重
    for sector in sector_pe_map:
        seen: set = set()
        deduped = []
        for dt, pe in sorted(sector_pe_map[sector], key=lambda x: x[0], reverse=True):
            if dt not in seen:
                seen.add(dt)
                deduped.append((dt, pe))
        sector_pe_map[sector] = deduped

    as_of = dates[0] if dates else ""
    valuations: List[SectorValuation] = []

    for sector, pe_series in sorted(sector_pe_map.items()):
        sector_cn = SECTOR_CN_MAP.get(sector, sector)
        sv = build_sector_valuation(sector=sector, sector_cn=sector_cn, pe_series=pe_series)
        valuations.append(sv)

    logger.info(
        "sector_valuation_compute_done",
        sectors=len(valuations),
        with_data=sum(1 for v in valuations if v.z_score is not None),
    )
    return SectorValuationResponse(as_of=as_of, sectors=valuations)
