"""行业（板块）级 regime 测试：对齐、特征、逐板块 walk-forward。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from app.services.regime.constants import MARKET_SYMBOL, SECTORS, VIX_SYMBOL
from app.services.regime.fetcher import align_sector_data
from app.services.regime.sector_features import (
    SECTOR_LABEL_WEIGHTS,
    build_sector_feature_series,
    stack_sector_features,
)
from app.services.regime.sector_pipeline import compute_sector_regimes


def _bar(d: str, c: float) -> dict:
    return {"date": d, "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6}


def _sector_bars(dates: list[str], n_sectors: int | None = None) -> dict[str, list[dict]]:
    syms = [MARKET_SYMBOL, VIX_SYMBOL]
    used = SECTORS if n_sectors is None else SECTORS[:n_sectors]
    syms += [s["symbol"] for s in used]
    return {s: [_bar(d, 100.0 + i) for i, d in enumerate(dates)] for s in syms}


def test_sector_label_weights_shape():
    assert SECTOR_LABEL_WEIGHTS.shape == (5,)


def test_align_sector_intersects_and_skips_missing_sector():
    dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    bars = _sector_bars(dates)
    # 某板块整只缺失 → 应被跳过，其余仍对齐
    bars[SECTORS[0]["symbol"]] = []
    md = align_sector_data(bars)
    assert SECTORS[0]["key"] not in md.sectors
    assert len(md.sectors) == len(SECTORS) - 1
    assert md.dates == [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    assert md.market_close.shape == (3,)


def test_align_sector_missing_market_raises():
    bars = _sector_bars(["2024-01-02", "2024-01-03"])
    bars[MARKET_SYMBOL] = []
    with pytest.raises(RuntimeError):
        align_sector_data(bars)


def test_build_sector_features_rs_vs_market():
    n = 60
    sector = np.cumprod(1 + np.full(n, 0.01)) * 100  # 板块每天 +1%
    market = np.cumprod(1 + np.full(n, 0.0)) * 100  # 大盘持平
    vix = np.full(n, 15.0)
    series = build_sector_feature_series(sector, sector * 1.01, sector * 0.99, np.full(n, 1e6), market, vix)
    m = stack_sector_features(series)
    assert m.shape == (n, 5)
    # 板块强于大盘 → RS 应为正（跳过前置 NaN）
    rs = series["rs_vs_market"]
    assert np.nanmean(rs) > 0


def _make_sector_market(t: int = 640):
    rng = np.random.default_rng(5)
    d0 = date(2021, 1, 1)
    dates = [d0 + timedelta(days=i) for i in range(t)]
    from app.services.regime.fetcher import SectorMarketData

    def walk(drift, vol):
        return np.cumprod(1 + rng.normal(drift, vol, t)) * 100

    market = walk(0.0003, 0.01)
    sectors = {}
    for s in SECTORS[:3]:
        sw = t // 2
        c = np.concatenate([walk(0.001, 0.01)[:sw], walk(-0.001, 0.02)[sw:]])
        sectors[s["key"]] = {
            "close": c,
            "high": c * 1.01,
            "low": c * 0.99,
            "volume": np.abs(rng.normal(1e6, 1e5, t)),
        }
    return SectorMarketData(
        dates=dates,
        vix_close=np.abs(rng.normal(18, 3, t)),
        market_close=market,
        sectors=sectors,
    )


def test_compute_sector_regimes_produces_per_sector_records():
    data = _make_sector_market()
    by_sector = compute_sector_regimes(data)
    assert set(by_sector.keys()) == set(data.sectors.keys())
    for recs in by_sector.values():
        assert len(recs) == len(data.dates)
        fitted = [r for r in recs if r.p_risk_off is not None]
        assert len(fitted) > 0
        for r in fitted:
            s = (r.p_risk_on or 0) + (r.p_neutral or 0) + (r.p_risk_off or 0)
            assert abs(s - 1.0) < 1e-6
            assert abs((r.factor_weight or 0) - (1.0 - (r.p_risk_off or 0))) < 1e-9
