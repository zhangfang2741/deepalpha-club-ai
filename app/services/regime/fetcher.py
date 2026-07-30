"""市场状态所需行情抓取与对齐（Financial Modeling Prep，走代理）。

从 FMP 拉取纳指、VIX、三篮子全部成分的日线，对齐到共同交易日索引，
输出供 features/engine 使用的对齐矩阵。

数据源选择 FMP 而非 yfinance：FMP 走仓库统一的 httpx + 代理链路（与 ETF/skills
模块一致），生产 Railway 直连、沙箱走 agent 代理均可；yfinance 的 curl_cffi
直连不经代理，在受控网络下会被拦截。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import httpx
import numpy as np

from app.core.config import settings
from app.core.logging import logger
from app.services.regime.constants import (
    CASH_BASKET,
    DEFENSE_BASKET,
    NASDAQ_SYMBOL,
    OFFENSE_BASKET,
    VIX_SYMBOL,
)

_FMP_BASE = "https://financialmodelingprep.com/stable"


@dataclass
class RegimeMarketData:
    """对齐后的市场数据（所有数组按 dates 顺序等长）。"""

    dates: list[date]
    qqq_close: np.ndarray
    qqq_high: np.ndarray
    qqq_low: np.ndarray
    qqq_volume: np.ndarray
    vix_close: np.ndarray
    offense_prices: np.ndarray  # (T, n_off)
    defense_prices: np.ndarray  # (T, n_def)
    cash_prices: np.ndarray  # (T, n_cash)


def _fmp_eod(symbol: str, from_: str, to: str) -> list[dict]:
    """抓取单只标的的日线 EOD（date/open/high/low/close/volume），失败返回空。"""
    url = f"{_FMP_BASE}/historical-price-eod/full"
    params = {"symbol": symbol, "from": from_, "to": to, "apikey": settings.FMP_API_KEY}
    try:
        resp = httpx.get(
            url,
            params=params,
            timeout=30,
            proxy=settings.HTTP_PROXY or settings.HTTPS_PROXY or None,
        )
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, dict) and "Error Message" in body:
            logger.warning("regime_fmp_error", symbol=symbol, detail=body.get("Error Message"))
            return []
        rows = body if isinstance(body, list) else body.get("historical", [])
    except Exception as exc:  # noqa: BLE001
        logger.exception("regime_fmp_fetch_failed", symbol=symbol, error=str(exc))
        return []
    return [
        {
            "date": r["date"][:10],
            "open": float(r.get("open") or 0.0),
            "high": float(r.get("high") or 0.0),
            "low": float(r.get("low") or 0.0),
            "close": float(r["close"]),
            "volume": float(r.get("volume") or 0.0),
        }
        for r in rows
        if r.get("close") is not None
    ]


def align_market_data(bars_by_symbol: dict[str, list[dict]]) -> RegimeMarketData:
    """把各标的的 EOD 列表对齐到共同交易日，构造 RegimeMarketData（纯函数，便于测试）。

    共同交易日 = 所有必需标的都有收盘价的日期交集，升序。
    """
    required = [NASDAQ_SYMBOL, VIX_SYMBOL, *OFFENSE_BASKET, *DEFENSE_BASKET, *CASH_BASKET]
    by_symbol: dict[str, dict[str, dict]] = {}
    for sym in required:
        rows = bars_by_symbol.get(sym) or []
        by_symbol[sym] = {r["date"]: r for r in rows}
        if not by_symbol[sym]:
            raise RuntimeError(f"缺少 {sym} 的行情，无法计算市场状态")

    common = set(by_symbol[NASDAQ_SYMBOL].keys())
    for sym in required:
        common &= set(by_symbol[sym].keys())
    if not common:
        raise RuntimeError("各标的无共同交易日，无法对齐")

    day_strs = sorted(common)
    dates = [date.fromisoformat(d) for d in day_strs]

    def close_vec(sym: str) -> np.ndarray:
        return np.array([by_symbol[sym][d]["close"] for d in day_strs], dtype=float)

    def matrix(syms: list[str]) -> np.ndarray:
        return np.column_stack([close_vec(s) for s in syms])

    qqq = by_symbol[NASDAQ_SYMBOL]
    return RegimeMarketData(
        dates=dates,
        qqq_close=close_vec(NASDAQ_SYMBOL),
        qqq_high=np.array([qqq[d]["high"] for d in day_strs], dtype=float),
        qqq_low=np.array([qqq[d]["low"] for d in day_strs], dtype=float),
        qqq_volume=np.array([qqq[d]["volume"] for d in day_strs], dtype=float),
        vix_close=close_vec(VIX_SYMBOL),
        offense_prices=matrix(OFFENSE_BASKET),
        defense_prices=matrix(DEFENSE_BASKET),
        cash_prices=matrix(CASH_BASKET),
    )


def fetch_regime_market_data(lookback_days: int = 1400) -> RegimeMarketData:
    """抓取并对齐 regime 所需的全部行情。

    Args:
        lookback_days: 日历回看天数，默认约 4 年（覆盖 MIN_FIT_HISTORY + 富余）。
    """
    symbols = [NASDAQ_SYMBOL, VIX_SYMBOL, *OFFENSE_BASKET, *DEFENSE_BASKET, *CASH_BASKET]
    seen: set[str] = set()
    uniq = [s for s in symbols if not (s in seen or seen.add(s))]

    end = date.today()
    start = end - timedelta(days=lookback_days)
    from_, to = start.isoformat(), end.isoformat()

    bars_by_symbol = {sym: _fmp_eod(sym, from_, to) for sym in uniq}
    empty = [s for s, rows in bars_by_symbol.items() if not rows]
    if empty:
        logger.warning("regime_market_symbols_empty", symbols=empty)
    return align_market_data(bars_by_symbol)
