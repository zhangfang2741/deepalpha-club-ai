"""三篮子相对强弱 → 合成 ODS / CF。

- ODS（Offense-Defense Spread）：进攻篮子相对防御篮子的滚动强弱。
- CF（Cash Flight）：现金篮子相对风险资产（进攻+防御）的滚动强弱，捕捉整体离场。

**关键**：RS 统一用滚动窗口口径（trailing_return over W），而非 rebase-since-基准日。
trailing_return 只依赖 [t-W, t] 的价格，追加新数据不会回改历史 ODS/CF，无前视偏差。
"""
from __future__ import annotations

import numpy as np

from app.services.regime.indicators import trailing_return


def basket_index(price_matrix: np.ndarray) -> np.ndarray:
    """由多只成分股的对齐收盘价构造等权篮子净值指数（起点 1.0）。

    Args:
        price_matrix: (T, n_symbols) 对齐后的收盘价（无缺失）。
    Returns:
        (T,) 等权篮子累计净值序列。
    """
    price_matrix = np.asarray(price_matrix, dtype=float)
    if price_matrix.ndim != 2 or price_matrix.shape[1] == 0:
        raise ValueError("price_matrix 必须是 (T, n_symbols) 且至少一列")
    # 每只成分股的日收益
    rets = np.zeros_like(price_matrix)
    rets[1:] = price_matrix[1:] / price_matrix[:-1] - 1.0
    # 等权平均 → 篮子日收益 → 累计净值
    basket_ret = rets.mean(axis=1)
    return np.cumprod(1.0 + basket_ret)


def compute_ods_cf(
    offense_prices: np.ndarray,
    defense_prices: np.ndarray,
    cash_prices: np.ndarray,
    window: int,
) -> tuple[np.ndarray, np.ndarray]:
    """由三篮子对齐价格矩阵计算 ODS、CF 序列（滚动窗口口径）。

    Args:
        offense_prices: (T, n_off) 进攻篮子成分收盘价
        defense_prices: (T, n_def) 防御篮子成分收盘价
        cash_prices: (T, n_cash) 现金篮子成分收盘价
        window: 滚动强弱窗口
    Returns:
        (ods, cf) 两个 (T,) 序列，前 window 个为 NaN。
    """
    offense_idx = basket_index(offense_prices)
    defense_idx = basket_index(defense_prices)
    cash_idx = basket_index(cash_prices)
    # 风险资产 = 进攻 + 防御 合并等权
    risk_idx = basket_index(np.hstack([offense_prices, defense_prices]))

    off_rs = trailing_return(offense_idx, window)
    def_rs = trailing_return(defense_idx, window)
    cash_rs = trailing_return(cash_idx, window)
    risk_rs = trailing_return(risk_idx, window)

    ods = off_rs - def_rs
    cf = cash_rs - risk_rs
    return ods, cf
