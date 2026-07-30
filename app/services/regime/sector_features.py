"""行业（板块）级 regime 特征。

每个板块独立拟合 HMM，特征取该板块自身的量价 + 相对大盘强弱：
`[板块收益, 板块已实现波动, VIX, 相对大盘强弱 RS, 板块 CMF]`

- RS_vs_market：板块滚动收益 − 大盘(SPY)滚动收益，衡量板块领先/落后大盘。
- 标签打分权重：+收益 −波动 −VIX +RS +CMF（越高越 risk_on）。
"""
from __future__ import annotations

import numpy as np

from app.services.regime.constants import (
    OBV_CMF_WINDOW,
    RETURN_WINDOW,
    RS_WINDOW,
    VOL_WINDOW,
)
from app.services.regime.indicators import cmf, realized_vol, trailing_return

SECTOR_FEATURE_NAMES = ["sector_ret", "sector_vol", "vix", "rs_vs_market", "sector_cmf"]

# 标签打分权重（对应上面特征顺序）：+收益 −波动 −VIX +RS +CMF
SECTOR_LABEL_WEIGHTS: np.ndarray = np.array([1.0, -1.0, -1.0, 1.0, 1.0])


def build_sector_feature_series(
    sector_close: np.ndarray,
    sector_high: np.ndarray,
    sector_low: np.ndarray,
    sector_volume: np.ndarray,
    market_close: np.ndarray,
    vix_close: np.ndarray,
) -> dict[str, np.ndarray]:
    """构造单个板块的每日原始特征序列（未标准化，含前置窗口 NaN）。"""
    sector_close = np.asarray(sector_close, dtype=float)
    ret = trailing_return(sector_close, RETURN_WINDOW)
    vol = realized_vol(sector_close, VOL_WINDOW)
    rs = trailing_return(sector_close, RS_WINDOW) - trailing_return(
        np.asarray(market_close, dtype=float), RS_WINDOW
    )
    cmf_v = cmf(sector_high, sector_low, sector_close, sector_volume, OBV_CMF_WINDOW)
    return {
        "sector_ret": ret,
        "sector_vol": vol,
        "vix": np.asarray(vix_close, dtype=float),
        "rs_vs_market": rs,
        "sector_cmf": cmf_v,
    }


def stack_sector_features(series: dict[str, np.ndarray]) -> np.ndarray:
    """按 SECTOR_FEATURE_NAMES 顺序堆叠成 (T, D) 矩阵。"""
    return np.column_stack([series[name] for name in SECTOR_FEATURE_NAMES])
