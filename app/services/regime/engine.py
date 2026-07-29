"""走-前向（walk-forward）状态引擎：月末冻结重估 + 逐日滤波后验。

严格杜绝前视偏差的三条规则（对应任务要求）：
1. **月末冻结重估**：只在每个自然月最后一个交易日，用「截至当日的全部历史」重估 HMM
   参数与标准化 scaler，参数在下一个月保持冻结。
2. **只用历史数据**：第 t 天用的参数来自 t 之前最近一次月末重估（严格过去），
   day t 从不用到未来数据。
3. **状态序列不回改**：每日后验用前向滤波 `filter_posteriors`（只看当天及之前），
   已产出的历史后验不会被未来数据改写。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from app.services.regime.constants import (
    COVAR_SHRINKAGE,
    MAX_SELF_TRANSITION,
    MIN_FIT_HISTORY,
    N_STATES,
    PERSIST_N_DAYS,
    POSTERIOR_TEMPERATURE,
    STATE_LABELS,
)
from app.services.regime.features import (
    IDX_CF,
    IDX_ODS,
    IDX_QQQ_RET,
    IDX_VIX,
    IDX_VOL,
)
from app.services.regime.hmm import (
    GaussianHMMParams,
    filter_posteriors,
    fit_gaussian_hmm,
)


@dataclass
class DailyRegime:
    """单个交易日的状态输出。"""

    date: date
    posteriors: dict[str, float]  # 各状态滤波后验
    label: str  # argmax 状态（原始）
    confirmed_label: str | None  # 连续 PERSIST_N_DAYS 同状态才确认，否则 None
    params_version: str | None  # 使用的参数版本（月末日期），None=历史不足未拟合


@dataclass
class RegimeResult:
    daily: list[DailyRegime] = field(default_factory=list)


def _month_key(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def _fit_scaler(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """返回 (mean, std)，std 下限保护。"""
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std = np.where(std < 1e-8, 1.0, std)
    return mean, std


def _label_mapping(params: GaussianHMMParams) -> list[str]:
    """把隐状态按「风险偏好得分」排序，映射到 逐利/观望/避险。

    得分（标准化空间的 means）：+纳指收益 −波动 −VIX +ODS −CF。
    得分最高→risk_on，最低→risk_off，中间→neutral。
    返回 state_index -> label 的列表。
    """
    m = params.means
    score = (
        m[:, IDX_QQQ_RET]
        - m[:, IDX_VOL]
        - m[:, IDX_VIX]
        + m[:, IDX_ODS]
        - m[:, IDX_CF]
    )
    order = np.argsort(-score)  # 得分降序：第0名最像 risk_on
    mapping = [""] * params.n_states
    for rank, state_idx in enumerate(order):
        mapping[state_idx] = STATE_LABELS[rank]
    return mapping


def _confirm_labels(labels: list[str | None], n: int) -> list[str | None]:
    """「持续 N 日」确认：连续 n 天同一 label 才输出该 label，否则 None。"""
    confirmed: list[str | None] = []
    for i, lab in enumerate(labels):
        if lab is None:
            confirmed.append(None)
            continue
        window = labels[max(0, i - n + 1) : i + 1]
        if len(window) == n and all(w == lab for w in window):
            confirmed.append(lab)
        else:
            confirmed.append(None)
    return confirmed


def run_walk_forward(
    dates: list[date],
    features: np.ndarray,
    valid_mask: np.ndarray,
    n_states: int = N_STATES,
    min_history: int = MIN_FIT_HISTORY,
    persist_n: int = PERSIST_N_DAYS,
    seed: int = 42,
    covar_shrinkage: float = COVAR_SHRINKAGE,
    max_self_transition: float = MAX_SELF_TRANSITION,
    temperature: float = POSTERIOR_TEMPERATURE,
) -> RegimeResult:
    """走-前向拟合并产出逐日滤波后验。

    Args:
        dates: 长度 T 的交易日列表（升序）。
        features: (T, D) 原始特征矩阵（可含 NaN 于前置窗口）。
        valid_mask: (T,) 布尔，标记特征无 NaN 的可用行。
        n_states: 隐状态数（逐利/观望/避险）。
        min_history: 首次拟合所需最小可用历史天数。
        persist_n: 「持续 N 日」确认所需连续天数。
        seed: HMM 初始化随机种子。
        covar_shrinkage: 协方差向池化方差收缩系数（抑制后验饱和）。
        max_self_transition: 自转移概率上限（掐断逐日复利式钉死）。
        temperature: 发射对数似然退火温度（软化后验为可用软概率）。
    """
    t = len(dates)
    features = np.asarray(features, dtype=float)

    # 只用可用行参与拟合/滤波；其余行输出 None
    valid_idx = np.where(valid_mask)[0]

    # 找到每个自然月最后一个「可用交易日」的全局索引 → 作为月末重估点
    month_end_positions: dict[tuple[int, int], int] = {}
    for gi in valid_idx:
        month_end_positions[_month_key(dates[gi])] = gi
    # 升序的月末全局索引列表
    month_ends = sorted(month_end_positions.values())

    # 为每个月末拟合冻结参数（只用截至该月末的可用历史）
    # 每个元素为：参数、scaler 均值、scaler 标准差、状态标签映射、版本串
    frozen: list[tuple[GaussianHMMParams, np.ndarray, np.ndarray, list[str], str]] = []
    frozen_endpos: list[int] = []
    for me in month_ends:
        hist_rows = valid_idx[valid_idx <= me]
        if len(hist_rows) < min_history:
            continue
        x_hist = features[hist_rows]
        mean, std = _fit_scaler(x_hist)
        x_std = (x_hist - mean) / std
        try:
            params = fit_gaussian_hmm(
                x_std,
                n_states=n_states,
                seed=seed,
                covar_shrinkage=covar_shrinkage,
                max_self_transition=max_self_transition,
            )
        except ValueError:
            continue
        label_map = _label_mapping(params)
        version = dates[me].isoformat()
        frozen.append((params, mean, std, label_map, version))
        frozen_endpos.append(me)

    # 逐日：用「该日之前最近一次月末冻结」的参数做滤波
    raw_labels: list[str | None] = [None] * t
    posterior_rows: list[dict[str, float] | None] = [None] * t
    version_rows: list[str | None] = [None] * t

    # 对每个冻结参数段，其管辖的天 = (该月末, 下个月末] 内的可用日
    for fi, me in enumerate(frozen_endpos):
        params, mean, std, label_map, version = frozen[fi]
        next_me = frozen_endpos[fi + 1] if fi + 1 < len(frozen_endpos) else t
        # 该段管辖的可用日：严格晚于 me、不晚于 next_me
        seg_days = valid_idx[(valid_idx > me) & (valid_idx <= next_me)]
        if len(seg_days) == 0:
            continue
        # 滤波序列从 0 到该段最后一天，参数固定 → 每行只依赖当天及之前，不回改
        upto = seg_days[-1]
        hist_rows = valid_idx[valid_idx <= upto]
        x_std = (features[hist_rows] - mean) / std
        post = filter_posteriors(params, x_std, temperature=temperature)
        # hist_rows 全局索引 → 在 post 中的行位置
        pos_of = {gi: p for p, gi in enumerate(hist_rows)}
        for gi in seg_days:
            row = post[pos_of[gi]]
            state_post = {label_map[k]: float(row[k]) for k in range(params.n_states)}
            best_state = int(np.argmax(row))
            raw_labels[gi] = label_map[best_state]
            posterior_rows[gi] = state_post
            version_rows[gi] = version

    confirmed = _confirm_labels(raw_labels, persist_n)

    result = RegimeResult()
    for gi in range(t):
        result.daily.append(
            DailyRegime(
                date=dates[gi],
                posteriors=posterior_rows[gi] or {lab: float("nan") for lab in STATE_LABELS},
                label=raw_labels[gi] or "",
                confirmed_label=confirmed[gi],
                params_version=version_rows[gi],
            )
        )
    return result
