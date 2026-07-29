"""量价与波动指标（真实 OBV / CMF / 已实现波动 / 滚动收益）。

全部为**滚动窗口**口径：第 t 个值只依赖 [t-W, t] 的数据，追加未来数据不改历史，
杜绝前视偏差。这里不做任何 rebase-since-基准日。
"""
from __future__ import annotations

import numpy as np


def daily_returns(close: np.ndarray) -> np.ndarray:
    """简单日收益，首日置 0，长度与输入一致。"""
    close = np.asarray(close, dtype=float)
    ret = np.zeros_like(close)
    ret[1:] = close[1:] / close[:-1] - 1.0
    return ret


def trailing_return(close: np.ndarray, window: int) -> np.ndarray:
    """滚动窗口累计收益 close_t / close_{t-window} - 1，前 window 个为 NaN。"""
    close = np.asarray(close, dtype=float)
    out = np.full_like(close, np.nan)
    if len(close) > window:
        out[window:] = close[window:] / close[:-window] - 1.0
    return out


def realized_vol(close: np.ndarray, window: int, annualize_days: int = 252) -> np.ndarray:
    """滚动已实现波动：日收益的滚动标准差 × sqrt(annualize_days)。

    前 window 个（不足一个完整窗口）为 NaN。
    """
    ret = daily_returns(close)
    n = len(ret)
    out = np.full(n, np.nan)
    scale = np.sqrt(annualize_days)
    for i in range(window, n):
        # 用 [i-window+1, i] 共 window 个日收益（跳过首日的占位 0 不影响窗口内）
        out[i] = np.std(ret[i - window + 1 : i + 1], ddof=1) * scale
    return out


def obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """真实 On-Balance Volume（累积）。

    上涨日 +volume，下跌日 -volume，平盘 0，首日 0。
    """
    close = np.asarray(close, dtype=float)
    volume = np.asarray(volume, dtype=float)
    out = np.zeros(len(close))
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            out[i] = out[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            out[i] = out[i - 1] - volume[i]
        else:
            out[i] = out[i - 1]
    return out


def obv_slope(close: np.ndarray, volume: np.ndarray, window: int) -> np.ndarray:
    """OBV 的滚动归一化斜率，作为量能确认信号（正=资金净流入趋势）。

    用窗口内 OBV 变化除以窗口内平均成交量，得到量纲无关的强度。
    前 window 个为 NaN。
    """
    o = obv(close, volume)
    volume = np.asarray(volume, dtype=float)
    n = len(o)
    out = np.full(n, np.nan)
    for i in range(window, n):
        avg_vol = np.mean(volume[i - window + 1 : i + 1])
        if avg_vol > 0:
            out[i] = (o[i] - o[i - window]) / (avg_vol * window)
    return out


def cmf(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int,
) -> np.ndarray:
    """真实 Chaikin Money Flow。

    CMF = sum(MFV, W) / sum(volume, W)，其中
    MFV = ((close-low) - (high-close)) / (high-low) * volume（high==low 时为 0）。
    前 window 个为 NaN。
    """
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    volume = np.asarray(volume, dtype=float)

    hl = high - low
    with np.errstate(divide="ignore", invalid="ignore"):
        mfm = np.where(hl > 0, ((close - low) - (high - close)) / hl, 0.0)
    mfv = mfm * volume

    n = len(close)
    out = np.full(n, np.nan)
    for i in range(window - 1, n):
        vol_sum = np.sum(volume[i - window + 1 : i + 1])
        if vol_sum > 0:
            out[i] = np.sum(mfv[i - window + 1 : i + 1]) / vol_sum
    return out
