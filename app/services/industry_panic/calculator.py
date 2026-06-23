"""行业恐慌指数计算：基于行业 ETF 日收盘价的 RSI(14) 衍生。

恐慌映射：panic = 100 - RSI
- RSI 低（价格急跌）→ panic 高（市场恐慌）
- RSI 高（价格强势）→ panic 低（市场平静）
"""

from __future__ import annotations

import datetime
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import logger

FMP_BASE_URL = "https://financialmodelingprep.com/stable"

# 11 个 GICS 一级行业 → 对应 SPDR Sector ETF
SECTOR_ETF_MAP: list[dict] = [
    {"sector_cn": "信息技术", "sector": "Information Technology", "symbol": "XLK"},
    {"sector_cn": "医疗保健", "sector": "Health Care",            "symbol": "XLV"},
    {"sector_cn": "金融",     "sector": "Financials",             "symbol": "XLF"},
    {"sector_cn": "可选消费", "sector": "Consumer Discretionary", "symbol": "XLY"},
    {"sector_cn": "必需消费", "sector": "Consumer Staples",       "symbol": "XLP"},
    {"sector_cn": "工业",     "sector": "Industrials",            "symbol": "XLI"},
    {"sector_cn": "能源",     "sector": "Energy",                 "symbol": "XLE"},
    {"sector_cn": "原材料",   "sector": "Materials",              "symbol": "XLB"},
    {"sector_cn": "通信服务", "sector": "Communication Services", "symbol": "XLC"},
    {"sector_cn": "房地产",   "sector": "Real Estate",            "symbol": "XLRE"},
    {"sector_cn": "公用事业", "sector": "Utilities",              "symbol": "XLU"},
]

RSI_PERIOD = 14
# 拉取约 1.5 年日线，保证 RSI 有足够的预热数据
FETCH_CALENDAR_DAYS = 550


def _fetch_closes(symbol: str) -> list[tuple[str, float]]:
    """从 FMP 拉取日 K 收盘价，返回 [(date, close), ...] 升序排列。"""
    today = datetime.date.today()
    from_date = (today - datetime.timedelta(days=FETCH_CALENDAR_DAYS)).isoformat()
    to_date = today.isoformat()
    url = (
        f"{FMP_BASE_URL}/historical-price-eod/full"
        f"?symbol={symbol}&from={from_date}&to={to_date}&apikey={settings.FMP_API_KEY}"
    )
    try:
        resp = httpx.get(
            url,
            timeout=20,
            proxy=settings.HTTP_PROXY or settings.HTTPS_PROXY or None,
        )
        resp.raise_for_status()
        body = resp.json()
        historical = body if isinstance(body, list) else body.get("historical", [])
    except Exception as e:
        logger.exception("industry_panic_fmp_fetch_failed", symbol=symbol, error=str(e))
        return []

    # FMP 返回降序，翻转为升序
    pairs = [(row["date"], float(row["close"])) for row in reversed(historical) if "close" in row]
    return pairs


def _rsi_series(closes: list[float], period: int = RSI_PERIOD) -> list[Optional[float]]:
    """Wilder 平滑 RSI 序列，长度与 closes 相同，前 period 个为 None。"""
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n <= period:
        return result

    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, n)]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, n)]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _rsi(ag: float, al: float) -> float:
        if al == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + ag / al)

    result[period] = _rsi(avg_gain, avg_loss)

    for i in range(period, n - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result[i + 1] = _rsi(avg_gain, avg_loss)

    return result


def compute_sector_panic(symbol: str) -> list[dict]:
    """计算单个行业 ETF 的历史恐慌指数序列。

    返回 [{"date": str, "rsi": float, "panic": float}, ...]
    """
    pairs = _fetch_closes(symbol)
    if not pairs:
        return []

    dates = [p[0] for p in pairs]
    closes = [p[1] for p in pairs]
    rsi_vals = _rsi_series(closes)

    result = []
    for date, rsi in zip(dates, rsi_vals, strict=False):
        if rsi is None:
            continue
        result.append({
            "date": date,
            "rsi": round(rsi, 2),
            "panic": round(100.0 - rsi, 2),
        })
    return result
