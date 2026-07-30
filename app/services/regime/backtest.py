"""因子叠加回测：验证 regime 门控（动量仓位 ×(1−p_避险)）是否降低回撤。

无前视对齐：第 t 天可交易的仓位只用 t-1 收盘时已知的信号与权重（内部对信号、
factor_weight 各滞后一日），再乘以 t 日收益。杜绝用当天信息交易当天收益。

指标全部为无量纲/年化标准口径，便于与基线并排比较。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TRADING_DAYS = 252


def equity_curve(daily_ret: np.ndarray) -> np.ndarray:
    """由日收益构造净值曲线（起点 1.0）。"""
    return np.cumprod(1.0 + np.asarray(daily_ret, dtype=float))


def max_drawdown(equity: np.ndarray) -> float:
    """最大回撤（正数，如 0.35 表示 -35%）。"""
    equity = np.asarray(equity, dtype=float)
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return float(-dd.min())


def annualized_return(daily_ret: np.ndarray, periods: int = TRADING_DAYS) -> float:
    """年化复合收益（CAGR）。"""
    daily_ret = np.asarray(daily_ret, dtype=float)
    n = daily_ret.size
    if n == 0:
        return 0.0
    total = float(np.prod(1.0 + daily_ret))
    if total <= 0:
        return -1.0
    return total ** (periods / n) - 1.0


def annualized_vol(daily_ret: np.ndarray, periods: int = TRADING_DAYS) -> float:
    """年化波动。"""
    daily_ret = np.asarray(daily_ret, dtype=float)
    if daily_ret.size < 2:
        return 0.0
    return float(np.std(daily_ret, ddof=1) * np.sqrt(periods))


def sharpe(daily_ret: np.ndarray, rf: float = 0.0, periods: int = TRADING_DAYS) -> float:
    """年化夏普比率（rf 为日无风险利率）。"""
    daily_ret = np.asarray(daily_ret, dtype=float)
    if daily_ret.size < 2:
        return 0.0
    excess = daily_ret - rf
    sd = np.std(excess, ddof=1)
    if sd == 0:
        return 0.0
    return float(np.mean(excess) / sd * np.sqrt(periods))


@dataclass
class StrategyMetrics:
    """单个策略的绩效指标。"""

    ann_return: float
    ann_vol: float
    sharpe: float
    max_drawdown: float
    calmar: float  # 年化收益 / 最大回撤
    final_equity: float

    @classmethod
    def from_returns(cls, daily_ret: np.ndarray) -> "StrategyMetrics":
        """从日收益序列计算全套指标。"""
        eq = equity_curve(daily_ret)
        mdd = max_drawdown(eq)
        ann = annualized_return(daily_ret)
        return cls(
            ann_return=ann,
            ann_vol=annualized_vol(daily_ret),
            sharpe=sharpe(daily_ret),
            max_drawdown=mdd,
            calmar=(ann / mdd) if mdd > 1e-9 else 0.0,
            final_equity=float(eq[-1]) if eq.size else 1.0,
        )


@dataclass
class OverlayBacktestResult:
    """基线 vs regime 门控 的回测对比结果。"""

    base: StrategyMetrics
    gated: StrategyMetrics
    base_equity: np.ndarray
    gated_equity: np.ndarray
    n_days: int


def run_overlay_backtest(
    asset_returns: np.ndarray,
    signal: np.ndarray,
    factor_weight: np.ndarray,
) -> OverlayBacktestResult:
    """对比「基线动量仓位」与「基线 ×(1−p_避险) 门控」。

    Args:
        asset_returns: (T,) 标的日收益（第 t 个为 t-1→t）。
        signal: (T,) 基线仓位信号（第 t 个为 t 日收盘时已知的目标仓位，∈[0,1]）。
        factor_weight: (T,) regime 因子权重 =(1−p_避险)，t 日收盘时已知；缺失(NaN)按 1 处理。

    无前视：信号与权重各滞后一日后作用于次日收益。
    """
    asset_returns = np.asarray(asset_returns, dtype=float)
    signal = np.asarray(signal, dtype=float)
    weight = np.asarray(factor_weight, dtype=float)
    weight = np.where(np.isnan(weight), 1.0, weight)

    # 滞后一日：t 日持仓由 t-1 决定
    pos_base = np.zeros_like(asset_returns)
    pos_gated = np.zeros_like(asset_returns)
    pos_base[1:] = np.nan_to_num(signal[:-1])
    pos_gated[1:] = np.nan_to_num(signal[:-1]) * weight[:-1]

    base_ret = pos_base * asset_returns
    gated_ret = pos_gated * asset_returns

    return OverlayBacktestResult(
        base=StrategyMetrics.from_returns(base_ret),
        gated=StrategyMetrics.from_returns(gated_ret),
        base_equity=equity_curve(base_ret),
        gated_equity=equity_curve(gated_ret),
        n_days=int(asset_returns.size),
    )


def momentum_signal(close: np.ndarray, window: int = 20) -> np.ndarray:
    """长仓动量信号：滚动窗口收益>0 则持仓 1，否则 0（前 window 个为 0）。"""
    close = np.asarray(close, dtype=float)
    sig = np.zeros_like(close)
    if close.size > window:
        mom = close[window:] / close[:-window] - 1.0
        sig[window:] = (mom > 0).astype(float)
    return sig
