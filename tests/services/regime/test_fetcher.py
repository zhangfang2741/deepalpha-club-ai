"""FMP 行情对齐测试（纯函数，无网络）。"""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from app.services.regime.constants import (
    CASH_BASKET,
    DEFENSE_BASKET,
    NASDAQ_SYMBOL,
    OFFENSE_BASKET,
    VIX_SYMBOL,
)
from app.services.regime.fetcher import align_market_data


def _bar(d: str, c: float) -> dict:
    return {"date": d, "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6}


def _full_bars(dates: list[str]) -> dict[str, list[dict]]:
    syms = [NASDAQ_SYMBOL, VIX_SYMBOL, *OFFENSE_BASKET, *DEFENSE_BASKET, *CASH_BASKET]
    return {s: [_bar(d, 100.0 + i) for i, d in enumerate(dates)] for s in syms}


def test_align_intersects_common_dates():
    dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    bars = _full_bars(dates)
    # 给某个防御标的少一天 → 交集应剔除该天
    bars[DEFENSE_BASKET[0]] = bars[DEFENSE_BASKET[0]][1:]  # 去掉首日
    md = align_market_data(bars)
    assert md.dates == [date(2024, 1, 3), date(2024, 1, 4)]
    assert md.qqq_close.shape == (2,)
    assert md.offense_prices.shape == (2, len(OFFENSE_BASKET))
    assert md.defense_prices.shape == (2, len(DEFENSE_BASKET))
    assert md.cash_prices.shape == (2, len(CASH_BASKET))


def test_align_sorted_ascending():
    dates = ["2024-03-05", "2024-03-01", "2024-03-04"]  # 乱序输入
    md = align_market_data(_full_bars(dates))
    iso = [d.isoformat() for d in md.dates]
    assert iso == sorted(iso)


def test_align_missing_symbol_raises():
    dates = ["2024-01-02", "2024-01-03"]
    bars = _full_bars(dates)
    bars[VIX_SYMBOL] = []  # VIX 缺失
    with pytest.raises(RuntimeError):
        align_market_data(bars)


def test_align_no_common_days_raises():
    bars = _full_bars(["2024-01-02", "2024-01-03"])
    bars[NASDAQ_SYMBOL] = [_bar("2023-12-31", 100.0)]  # 与其它标的无交集
    with pytest.raises(RuntimeError):
        align_market_data(bars)


def test_aligned_data_feeds_pipeline():
    # 对齐结果应能直接喂给 compute_regime_from_market（哪怕历史不足只出空后验）
    from app.services.regime.pipeline import compute_regime_from_market

    dates = [f"2024-{m:02d}-15" for m in range(1, 13)]
    md = align_market_data(_full_bars(dates))
    recs = compute_regime_from_market(md)
    assert len(recs) == len(dates)
    assert all(not np.isnan(r.vix) for r in recs if r.vix is not None)
