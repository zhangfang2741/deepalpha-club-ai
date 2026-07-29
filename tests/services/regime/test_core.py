"""regime 核心数值测试：HMM 拟合、无前视、真实 OBV/CMF、滚动 ODS/CF。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from app.services.regime.baskets import basket_index, compute_ods_cf
from app.services.regime.engine import run_walk_forward
from app.services.regime.features import stack_features
from app.services.regime.hmm import filter_posteriors, fit_gaussian_hmm
from app.services.regime.indicators import (
    cmf,
    obv,
    realized_vol,
    trailing_return,
)


def test_obv_matches_manual():
    close = np.array([10.0, 11.0, 10.5, 10.5, 12.0])
    volume = np.array([100.0, 200.0, 150.0, 120.0, 300.0])
    o = obv(close, volume)
    # 逐日：0, +200, -150, 0(平盘), +300
    assert o.tolist() == [0.0, 200.0, 50.0, 50.0, 350.0]


def test_cmf_matches_manual():
    high = np.array([2.0, 2.0])
    low = np.array([0.0, 0.0])
    close = np.array([2.0, 0.0])
    volume = np.array([100.0, 100.0])
    # MFM: 第一天 ((2-0)-(2-2))/2 = 1；第二天 ((0-0)-(2-0))/2 = -1
    # window=2: sum(mfv)= (1*100 + -1*100)=0，/200 = 0
    out = cmf(high, low, close, volume, window=2)
    assert np.isnan(out[0])
    assert abs(out[1] - 0.0) < 1e-9


def test_cmf_high_equals_low_no_div_zero():
    high = np.array([5.0, 5.0])
    low = np.array([5.0, 5.0])
    close = np.array([5.0, 5.0])
    volume = np.array([100.0, 100.0])
    out = cmf(high, low, close, volume, window=2)
    assert out[1] == 0.0  # high==low → MFM=0，不产生除零


def test_trailing_return_is_rolling_no_rewrite():
    # 滚动窗口口径：追加新数据不改历史值（杜绝 rebase-since 回改）
    rng = np.random.default_rng(0)
    close = np.cumprod(1 + rng.normal(0, 0.01, 200)) * 100
    tr_full = trailing_return(close, 20)
    tr_short = trailing_return(close[:150], 20)
    # 前 150 个应完全一致
    np.testing.assert_allclose(
        tr_full[:150][~np.isnan(tr_full[:150])],
        tr_short[~np.isnan(tr_short)],
    )


def test_realized_vol_positive_and_windowed():
    rng = np.random.default_rng(1)
    close = np.cumprod(1 + rng.normal(0, 0.02, 100)) * 100
    rv = realized_vol(close, 20)
    assert np.all(np.isnan(rv[:20]))
    assert np.all(rv[20:] > 0)


def test_basket_index_equal_weight():
    prices = np.array([[10.0, 20.0], [11.0, 20.0]])  # 第一只+10%，第二只0%
    idx = basket_index(prices)
    # 等权日收益 = 5%
    assert abs(idx[1] - 1.05) < 1e-9


def test_ods_cf_rolling_no_rewrite():
    rng = np.random.default_rng(2)
    n = 200

    def gen(k):
        return np.cumprod(1 + rng.normal(0.0002, 0.01, (n, k)), axis=0) * 100

    off, dfn, cash = gen(4), gen(3), gen(2)
    ods_full, cf_full = compute_ods_cf(off, dfn, cash, 20)
    ods_short, cf_short = compute_ods_cf(off[:150], dfn[:150], cash[:150], 20)
    # 追加数据后前 150 个 ODS/CF 不变
    np.testing.assert_allclose(ods_full[:150], ods_short, equal_nan=True)
    np.testing.assert_allclose(cf_full[:150], cf_short, equal_nan=True)


def test_hmm_recovers_two_regimes():
    # 合成两状态：状态A 均值高，状态B 均值低，可分离
    rng = np.random.default_rng(7)
    seg = 150
    a = rng.normal(2.0, 0.3, (seg, 2))
    b = rng.normal(-2.0, 0.3, (seg, 2))
    x = np.vstack([a, b, a, b])
    params = fit_gaussian_hmm(x, n_states=2, seed=1)
    post = filter_posteriors(params, x)
    # 两个高均值状态之一应主导前 150 天
    assert post.shape == (x.shape[0], 2)
    # 每行归一
    np.testing.assert_allclose(post.sum(axis=1), 1.0, atol=1e-6)
    # 拟合的两状态 means 应明显分离
    sep = np.abs(params.means[0] - params.means[1]).max()
    assert sep > 2.0


def test_filter_posterior_no_lookahead():
    # 关键：滤波后验第 t 行只依赖前 t 个观测，追加未来数据不回改
    rng = np.random.default_rng(9)
    x = np.vstack([rng.normal(2, 0.3, (100, 2)), rng.normal(-2, 0.3, (100, 2))])
    params = fit_gaussian_hmm(x, n_states=2, seed=1)
    post_full = filter_posteriors(params, x)
    post_trunc = filter_posteriors(params, x[:120])
    np.testing.assert_allclose(post_full[:120], post_trunc, atol=1e-9)


def test_walk_forward_no_rewrite_and_labels():
    # 端到端：走-前向后验不回改 + 参数版本按月冻结
    rng = np.random.default_rng(11)
    t = 700
    d0 = date(2021, 1, 1)
    dates = [d0 + timedelta(days=i) for i in range(t)]
    # 构造有 regime 切换的特征
    base = np.zeros((t, 5))
    switch = t // 2
    base[:switch] = rng.normal([0.05, 0.1, 15, 0.03, -0.02], 0.02, (switch, 5))
    base[switch:] = rng.normal([-0.05, 0.3, 30, -0.03, 0.02], 0.02, (t - switch, 5))
    feats = base
    valid = np.ones(t, dtype=bool)

    res_full = run_walk_forward(dates, feats, valid, min_history=252)
    res_trunc = run_walk_forward(dates[:600], feats[:600], valid[:600], min_history=252)

    # 已确认标签在截断前后一致（不回改）
    for i in range(600):
        a = res_full.daily[i]
        b = res_trunc.daily[i]
        assert a.params_version == b.params_version
        if a.posteriors and not np.isnan(list(a.posteriors.values())[0]):
            for k in a.posteriors:
                assert abs(a.posteriors[k] - b.posteriors[k]) < 1e-6


def test_stack_features_order():
    series = {
        "qqq_ret": np.array([1.0, 2.0]),
        "realized_vol": np.array([3.0, 4.0]),
        "vix": np.array([5.0, 6.0]),
        "ods": np.array([7.0, 8.0]),
        "cf": np.array([9.0, 10.0]),
    }
    m = stack_features(series)
    assert m.shape == (2, 5)
    assert m[0].tolist() == [1.0, 3.0, 5.0, 7.0, 9.0]
