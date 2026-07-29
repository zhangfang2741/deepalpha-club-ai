"""regime pipeline 编排测试（纯计算路径，无网络/DB）。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from app.services.regime.fetcher import RegimeMarketData
from app.services.regime.pipeline import compute_regime_from_market


def _make_market(t: int = 700) -> RegimeMarketData:
    rng = np.random.default_rng(3)
    d0 = date(2021, 1, 1)
    dates = [d0 + timedelta(days=i) for i in range(t)]

    def walk(k: int, drift: float, vol: float) -> np.ndarray:
        return np.cumprod(1 + rng.normal(drift, vol, (t, k)), axis=0) * 100

    switch = t // 2
    # 前半 risk_on：进攻强、波动低；后半 risk_off：防御/现金强、波动高
    off = np.vstack([walk(4, 0.001, 0.01)[:switch], walk(4, -0.001, 0.02)[switch:]])
    dfn = walk(3, 0.0003, 0.008)
    cash = walk(2, 0.0001, 0.001)
    qqq = off.mean(axis=1)
    vix = np.concatenate([np.full(switch, 15.0), np.full(t - switch, 30.0)])
    vix = vix + rng.normal(0, 1, t)
    volume = np.abs(rng.normal(1e6, 1e5, t))

    return RegimeMarketData(
        dates=dates,
        qqq_close=qqq,
        qqq_high=qqq * 1.01,
        qqq_low=qqq * 0.99,
        qqq_volume=volume,
        vix_close=vix,
        offense_prices=off,
        defense_prices=dfn,
        cash_prices=cash,
    )


def test_compute_regime_produces_records():
    data = _make_market()
    records = compute_regime_from_market(data)
    assert len(records) == len(data.dates)

    # 有拟合结果的日子后验三者近似和为 1，factor_weight = 1 - p_避险
    fitted = [r for r in records if r.p_risk_off is not None]
    assert len(fitted) > 0
    for r in fitted:
        s = (r.p_risk_on or 0) + (r.p_neutral or 0) + (r.p_risk_off or 0)
        assert abs(s - 1.0) < 1e-6
        assert abs((r.factor_weight or 0) - (1.0 - (r.p_risk_off or 0))) < 1e-9

    # 量价指标应被计算（非全空）
    assert any(r.obv_slope is not None for r in records)
    assert any(r.cmf is not None for r in records)

    # 前 MIN_FIT_HISTORY 段没有参数版本（历史不足不拟合）
    assert records[0].params_version is None


def test_softening_reduces_posterior_saturation():
    # 机制测试：退火（协方差收缩+转移封顶+温度）应显著软化后验，
    # 而非在人为可分的合成数据上强求某个绝对软度阈值。
    import numpy as np

    from app.services.regime.constants import (
        COVAR_SHRINKAGE,
        MAX_SELF_TRANSITION,
        POSTERIOR_TEMPERATURE,
    )
    from app.services.regime.engine import run_walk_forward
    from app.services.regime.features import build_feature_series, stack_features

    data = _make_market(700)
    series = build_feature_series(
        data.qqq_close, data.vix_close, data.offense_prices,
        data.defense_prices, data.cash_prices,
    )
    feats = stack_features(series)
    valid = np.asarray(~np.isnan(feats).any(axis=1), dtype=bool)

    def maxpost_stats(**kw) -> tuple[float, float]:
        res = run_walk_forward(data.dates, feats, valid, **kw)
        mx = np.array([
            max(d.posteriors.values())
            for d in res.daily
            if d.params_version is not None
        ])
        return float(mx.mean()), float((mx < 0.95).mean())  # 均值, 软占比

    raw_mean, raw_soft = maxpost_stats(
        covar_shrinkage=0.0, max_self_transition=1.0, temperature=1.0
    )
    soft_mean, soft_soft = maxpost_stats(
        covar_shrinkage=COVAR_SHRINKAGE,
        max_self_transition=MAX_SELF_TRANSITION,
        temperature=POSTERIOR_TEMPERATURE,
    )
    # 退火后：平均 max 后验更低、软后验（<0.95）占比更高
    assert soft_mean < raw_mean - 0.01
    assert soft_soft > raw_soft * 1.5


def test_records_are_date_sorted_and_unique():
    data = _make_market(400)
    records = compute_regime_from_market(data)
    dates = [r.trade_date for r in records]
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))
