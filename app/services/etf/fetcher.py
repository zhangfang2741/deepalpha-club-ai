"""ETF OHLCV 数据抓取与资金流计算（Financial Modeling Prep API）。

资金流代理指标：美元成交量 = Volume × Close。
FMP 免费版每日限额 250 次请求，Redis 缓存（TTL 1h）可有效控制调用量。
"""

import datetime
from typing import List

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.etf import ETFSummary, FlowDataPoint

TRACKED_ETFS: List[dict] = [
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "category": "Equity"},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "category": "Equity"},
    {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "category": "Equity"},
    {"symbol": "DIA", "name": "SPDR Dow Jones Industrial Average ETF", "category": "Equity"},
    {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF", "category": "Equity"},
    {"symbol": "GLD", "name": "SPDR Gold Shares", "category": "Commodities"},
    {"symbol": "SLV", "name": "iShares Silver Trust", "category": "Commodities"},
    {"symbol": "USO", "name": "United States Oil Fund", "category": "Commodities"},
    {"symbol": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "category": "Fixed Income"},
    {"symbol": "AGG", "name": "iShares Core U.S. Aggregate Bond ETF", "category": "Fixed Income"},
    {"symbol": "BND", "name": "Vanguard Total Bond Market ETF", "category": "Fixed Income"},
    {"symbol": "XLF", "name": "Financial Select Sector SPDR Fund", "category": "Sector"},
    {"symbol": "XLK", "name": "Technology Select Sector SPDR Fund", "category": "Sector"},
    {"symbol": "XLE", "name": "Energy Select Sector SPDR Fund", "category": "Sector"},
    {"symbol": "XLV", "name": "Health Care Select Sector SPDR Fund", "category": "Sector"},
    {"symbol": "EFA", "name": "iShares MSCI EAFE ETF", "category": "International"},
    {"symbol": "EEM", "name": "iShares MSCI Emerging Markets ETF", "category": "International"},
    {"symbol": "VEA", "name": "Vanguard FTSE Developed Markets ETF", "category": "International"},
]

_FMP_BASE = "https://financialmodelingprep.com/api/v3"

# period → FMP timeseries 天数（ytd 单独处理）
_TIMESERIES_MAP = {
    "1w": 7,
    "1mo": 31,
    "3mo": 92,
    "1y": 365,
}


def _build_url(symbol: str, period: str) -> str:
    """构造 FMP historical-price-full 请求 URL。"""
    api_key = settings.FMP_API_KEY
    if period == "ytd":
        start = datetime.date(datetime.date.today().year, 1, 1).isoformat()
        today = datetime.date.today().isoformat()
        return f"{_FMP_BASE}/historical-price-full/{symbol}?from={start}&to={today}&apikey={api_key}"
    timeseries = _TIMESERIES_MAP.get(period, 31)
    return f"{_FMP_BASE}/historical-price-full/{symbol}?timeseries={timeseries}&apikey={api_key}"


def fetch_etf_flows(symbol: str, period: str) -> List[FlowDataPoint]:
    """抓取单只 ETF 的 OHLCV 历史数据并计算资金流指标。

    Args:
        symbol: ETF 代码（如 "SPY"）
        period: 时间周期，取值 "1w" / "1mo" / "3mo" / "ytd" / "1y"

    Returns:
        按日期升序排列的 FlowDataPoint 列表；数据为空或请求失败时返回 []
    """
    url = _build_url(symbol, period)
    try:
        resp = httpx.get(url, timeout=15)
        resp.raise_for_status()
        historical = resp.json().get("historical", [])
    except Exception as e:
        logger.exception("fmp_fetch_failed", symbol=symbol, period=period, error=str(e))
        return []

    if not historical:
        logger.warning("fmp_empty_data", symbol=symbol, period=period)
        return []

    # FMP 返回降序（最新在前），反转为升序处理
    historical = list(reversed(historical))

    points: List[FlowDataPoint] = []
    prev_close: float | None = None

    for row in historical:
        close = float(row["close"])
        volume = int(row.get("volume") or 0)
        dollar_volume = close * volume

        return_pct = 0.0 if prev_close is None else (close - prev_close) / prev_close * 100

        points.append(
            FlowDataPoint(
                symbol=symbol,
                date=datetime.date.fromisoformat(row["date"]),
                close=round(close, 4),
                volume=volume,
                dollar_volume=round(dollar_volume, 2),
                return_pct=round(return_pct, 4),
            )
        )
        prev_close = close

    return points


def fetch_etf_list_summary(period: str) -> List[ETFSummary]:
    """抓取所有跟踪 ETF 在指定周期内的汇总数据。

    注意：会对每只 ETF 发起一次 FMP 请求（共 18 次）。
    调用方应通过 Redis 缓存（TTL 1h）控制总调用量。

    Args:
        period: 时间周期，取值 "1w" / "1mo" / "3mo" / "ytd" / "1y"

    Returns:
        所有 ETF 的 ETFSummary 列表；数据获取失败的 ETF 跳过
    """
    summaries: List[ETFSummary] = []
    for etf_meta in TRACKED_ETFS:
        symbol = etf_meta["symbol"]
        flows = fetch_etf_flows(symbol, period)
        if not flows:
            continue

        current_price = flows[-1].close
        first_close = flows[0].close
        price_change_pct = (current_price - first_close) / first_close * 100 if first_close else 0.0
        period_dollar_volume = sum(p.dollar_volume for p in flows)

        summaries.append(
            ETFSummary(
                symbol=symbol,
                name=etf_meta["name"],
                category=etf_meta["category"],
                current_price=round(current_price, 4),
                price_change_pct=round(price_change_pct, 4),
                period_dollar_volume=round(period_dollar_volume, 2),
            )
        )
    return summaries
