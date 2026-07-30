"""regime 回测指标与叠加机制测试。"""
from __future__ import annotations

import numpy as np

from app.services.regime.backtest import (
    annualized_return,
    equity_curve,
    max_drawdown,
    momentum_signal,
    run_overlay_backtest,
    sharpe,
)


def test_equity_curve_and_drawdown_known():
    # +10%, -50%, +100% → 净值 1.1, 0.55, 1.1
    ret = np.array([0.10, -0.50, 1.00])
    eq = equity_curve(ret)
    np.testing.assert_allclose(eq, [1.1, 0.55, 1.1])
    # 峰值 1.1 → 谷底 0.55，回撤 50%
    assert abs(max_drawdown(eq) - 0.5) < 1e-9


def test_annualized_return_flat():
    # 全 0 收益 → 年化 0
    assert abs(annualized_return(np.zeros(100))) < 1e-12


def test_sharpe_zero_when_constant():
    assert sharpe(np.full(50, 0.001)) == 0.0  # 无波动 → 0


def test_momentum_signal_basic():
    close = np.concatenate([np.linspace(100, 120, 30), np.linspace(120, 90, 30)])
    sig = momentum_signal(close, window=20)
    assert np.all(sig[:20] == 0)  # 预热段无持仓
    assert set(np.unique(sig)).issubset({0.0, 1.0})


def test_overlay_no_lookahead_alignment():
    # 仓位滞后一日：t 日收益由 t-1 信号决定
    ret = np.array([0.0, 0.10, -0.10, 0.05])
    signal = np.array([1.0, 0.0, 0.0, 0.0])  # 仅第0日给出满仓信号
    fw = np.ones(4)
    res = run_overlay_backtest(ret, signal, fw)
    # 只有第1日持仓（由第0日信号），赚 0.10；其余仓位 0
    np.testing.assert_allclose(res.base_equity, [1.0, 1.10, 1.10, 1.10])


def test_gate_reduces_drawdown_on_regime_data():
    # 构造：前半上涨（逐利），后半急跌（避险）。门控在避险期把仓位压低。
    n = 200
    up = np.full(n // 2, 0.004)
    down = np.full(n // 2, -0.006)
    ret = np.concatenate([up, down])
    close = np.cumprod(1 + ret) * 100
    signal = momentum_signal(close, window=10)
    # 避险后验：前半≈0，后半≈0.9 → factor_weight 前半≈1，后半≈0.1
    p_off = np.concatenate([np.full(n // 2, 0.0), np.full(n // 2, 0.9)])
    fw = 1.0 - p_off
    res = run_overlay_backtest(ret, signal, fw)
    # 门控最大回撤应显著小于基线
    assert res.gated.max_drawdown < res.base.max_drawdown
    # 且门控最终净值不低于基线（避开了下跌段）
    assert res.gated.final_equity >= res.base.final_equity
