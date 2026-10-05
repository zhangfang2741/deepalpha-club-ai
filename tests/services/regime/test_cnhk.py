"""A 股 / 港股大盘状态：配置、对齐、波动比、整条计算（纯函数，不联网不连库）。"""
from datetime import date, timedelta

import numpy as np
import pytest

from app.services.regime import cnhk
from app.services.regime.cnhk import MARKET_CONFIGS, align_market_data, compute_records, vol_ratio


def _days(n: int, start: date = date(2021, 1, 4)) -> list[str]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bars(days: list[str], seed: int, drift: float = 0.0004, vol: float = 0.01) -> list[dict]:
    rng = np.random.default_rng(seed)
    close = 10 * np.cumprod(1 + rng.normal(drift, vol, len(days)))
    return [{"time": d, "open": c, "high": c * 1.01, "low": c * 0.99, "close": float(c), "volume": 1e6}
            for d, c in zip(days, close, strict=True)]


def _all_bars(market: str, n: int = 700) -> dict[str, list[dict]]:
    days = _days(n)
    return {sym: _bars(days, i, vol=0.0005 if sym in MARKET_CONFIGS[market].cash else 0.012)
            for i, sym in enumerate(MARKET_CONFIGS[market].symbols)}


def test_configs_have_all_baskets_and_no_overlap():
    for market, cfg in MARKET_CONFIGS.items():
        assert cfg.offense and cfg.defense and cfg.cash, market
        baskets = [set(cfg.offense), set(cfg.defense), set(cfg.cash)]
        assert not (baskets[0] & baskets[1] or baskets[0] & baskets[2] or baskets[1] & baskets[2])
        assert len(cfg.symbols) == len(set(cfg.symbols))
    assert set(cnhk.CLOSE_HOUR_UTC) == set(cnhk.TRIGGER_UTC) == set(MARKET_CONFIGS)


def test_symbols_use_yahoo_exchange_suffixes():
    for sym in MARKET_CONFIGS["cn"].symbols:
        assert sym.endswith((".SS", ".SZ"))
    for sym in MARKET_CONFIGS["hk"].symbols:
        assert sym.endswith(".HK")


def test_vol_ratio_rises_when_recent_volatility_expands():
    rng = np.random.default_rng(0)
    calm = rng.normal(0, 0.005, 200)
    wild = rng.normal(0, 0.03, 30)
    close = 100 * np.cumprod(1 + np.concatenate([calm, wild]))
    ratio = vol_ratio(close)
    assert np.isnan(ratio[:cnhk.LONG_VOL_WINDOW]).all()
    assert ratio[199] < 1.3 and ratio[-1] > 1.5


def test_align_uses_common_days_and_maps_benchmark_and_baskets():
    market = "hk"
    bars = _all_bars(market, 300)
    drop = bars[MARKET_CONFIGS[market].defense[0]][5]["time"]
    bars[MARKET_CONFIGS[market].defense[0]] = [b for b in bars[MARKET_CONFIGS[market].defense[0]] if b["time"] != drop]
    data = align_market_data(MARKET_CONFIGS[market], bars)
    assert date.fromisoformat(drop) not in data.dates and len(data.dates) == 299
    cfg = MARKET_CONFIGS[market]
    assert data.offense_prices.shape == (299, len(cfg.offense))
    assert data.defense_prices.shape == (299, len(cfg.defense))
    assert data.cash_prices.shape == (299, len(cfg.cash))
    assert len(data.vix_close) == 299 and np.isnan(data.vix_close[0])


def test_align_raises_when_a_symbol_has_no_data():
    bars = _all_bars("cn", 300)
    bars[MARKET_CONFIGS["cn"].cash[0]] = []
    with pytest.raises(RuntimeError, match="缺少"):
        align_market_data(MARKET_CONFIGS["cn"], bars)


@pytest.mark.parametrize("market", ["cn", "hk"])
def test_compute_records_yields_posteriors_after_min_history(market):
    records = compute_records(market, _all_bars(market, 700))
    assert len(records) == 700
    fitted = [r for r in records if r.p_risk_on is not None]
    assert fitted, "历史足够时应有后验"
    last = fitted[-1]
    assert abs(last.p_risk_on + last.p_neutral + last.p_risk_off - 1) < 1e-6
    assert last.regime_label in {"risk_on", "neutral", "risk_off"}
    # 前面历史不足的日子没有后验（不乱拟合）
    assert records[0].p_risk_on is None
