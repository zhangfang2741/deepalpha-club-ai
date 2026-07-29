"""HMM 特征矩阵构造：[纳指收益, 已实现波动, VIX, ODS, CF]。"""
from __future__ import annotations

import numpy as np

from app.services.regime.baskets import compute_ods_cf
from app.services.regime.constants import (
    RETURN_WINDOW,
    RS_WINDOW,
    VOL_WINDOW,
)
from app.services.regime.indicators import realized_vol, trailing_return

# 特征列顺序（全局唯一口径，engine/label 依赖此顺序）
FEATURE_NAMES = ["qqq_ret", "realized_vol", "vix", "ods", "cf"]
IDX_QQQ_RET = 0
IDX_VOL = 1
IDX_VIX = 2
IDX_ODS = 3
IDX_CF = 4


def build_feature_series(
    qqq_close: np.ndarray,
    vix_close: np.ndarray,
    offense_prices: np.ndarray,
    defense_prices: np.ndarray,
    cash_prices: np.ndarray,
) -> dict[str, np.ndarray]:
    """构造每日原始特征序列（未标准化），含 NaN 于前置窗口。

    所有输入须已按同一交易日索引对齐（等长）。
    """
    qqq_close = np.asarray(qqq_close, dtype=float)
    vix_close = np.asarray(vix_close, dtype=float)

    qqq_ret = trailing_return(qqq_close, RETURN_WINDOW)
    rv = realized_vol(qqq_close, VOL_WINDOW)
    ods, cf = compute_ods_cf(offense_prices, defense_prices, cash_prices, RS_WINDOW)

    return {
        "qqq_ret": qqq_ret,
        "realized_vol": rv,
        "vix": vix_close,
        "ods": ods,
        "cf": cf,
    }


def stack_features(series: dict[str, np.ndarray]) -> np.ndarray:
    """按 FEATURE_NAMES 顺序堆叠成 (T, D) 矩阵。"""
    return np.column_stack([series[name] for name in FEATURE_NAMES])
