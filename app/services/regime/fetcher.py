"""市场状态所需行情抓取与对齐（yfinance）。

抓取纳指、VIX、三篮子全部成分的日线，并对齐到共同交易日索引，
输出供 features/engine 使用的对齐矩阵。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

from app.core.logging import logger
from app.services.regime.constants import (
    CASH_BASKET,
    DEFENSE_BASKET,
    NASDAQ_SYMBOL,
    OFFENSE_BASKET,
    VIX_SYMBOL,
)


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


def _download(symbols: list[str], start: date, end: date) -> pd.DataFrame:
    """下载多 symbol 日线，返回 auto_adjust 后的 DataFrame。"""
    df = yf.download(
        symbols,
        start=start.isoformat(),
        end=end.isoformat(),
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    return df if df is not None else pd.DataFrame()


def _field_frame(df: pd.DataFrame, field: str, symbols: list[str]) -> pd.DataFrame:
    """从 yfinance（可能 MultiIndex）中取出某字段的 (index=date, columns=symbols) 表。"""
    if hasattr(df.columns, "levels"):
        sub = df[field]
    else:
        # 单 symbol 情形
        sub = df[[field]]
        sub.columns = symbols
    return pd.DataFrame(sub)


def fetch_regime_market_data(lookback_days: int = 1400) -> RegimeMarketData:
    """抓取并对齐 regime 所需的全部行情。

    Args:
        lookback_days: 日历回看天数，默认约 4 年（覆盖 MIN_FIT_HISTORY + 富余）。
    """
    all_symbols = [NASDAQ_SYMBOL, VIX_SYMBOL, *OFFENSE_BASKET, *DEFENSE_BASKET, *CASH_BASKET]
    # 去重且保序
    seen: set[str] = set()
    uniq = [s for s in all_symbols if not (s in seen or seen.add(s))]

    end = date.today()
    start = end - timedelta(days=lookback_days)
    df = _download(uniq, start, end)
    if df is None or df.empty:
        logger.warning("regime_market_download_empty")
        raise RuntimeError("行情下载为空，无法计算市场状态")

    close = _field_frame(df, "Close", uniq)
    high = _field_frame(df, "High", uniq)
    low = _field_frame(df, "Low", uniq)
    volume = _field_frame(df, "Volume", uniq)

    # 以纳指非缺失日为基准，dropna 对齐所有 symbol 收盘价
    close = close.dropna(how="any")
    common_index = close.index
    high = high.reindex(common_index)
    low = low.reindex(common_index)
    volume = volume.reindex(common_index)

    dates = [idx.date() for idx in common_index]

    def col(frame: pd.DataFrame, sym: str) -> np.ndarray:
        return frame[sym].to_numpy(dtype=float)

    def matrix(frame: pd.DataFrame, syms: list[str]) -> np.ndarray:
        return np.column_stack([col(frame, s) for s in syms])

    return RegimeMarketData(
        dates=dates,
        qqq_close=col(close, NASDAQ_SYMBOL),
        qqq_high=col(high, NASDAQ_SYMBOL),
        qqq_low=col(low, NASDAQ_SYMBOL),
        qqq_volume=col(volume, NASDAQ_SYMBOL),
        vix_close=col(close, VIX_SYMBOL),
        offense_prices=matrix(close, OFFENSE_BASKET),
        defense_prices=matrix(close, DEFENSE_BASKET),
        cash_prices=matrix(close, CASH_BASKET),
    )
