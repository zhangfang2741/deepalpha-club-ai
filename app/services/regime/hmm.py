"""纯 numpy 实现的高斯 HMM（对角协方差）。

设计目标（对应任务「必须做对」的坑）：
- **真拟合**：用 Baum-Welch（EM）在对数域拟合 startprob / transmat / means / covars，
  而不是用 softmax 硬凑后验。
- **状态序列不回改**：对外提供 `filter_posteriors`（仅前向 alpha，即滤波后验），
  第 t 天的后验只依赖 x_1..x_t，追加未来数据不会改写历史后验，杜绝前视偏差。
- **可复现**：初始化确定（分位数切分 + 固定 seed），同一份数据拟合结果稳定。

emissions 采用多元高斯、对角协方差；特征在外部已做标准化。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_LOG_2PI = float(np.log(2.0 * np.pi))
_MIN_VAR = 1e-4  # 方差下限，防止退化为 delta 分布导致数值爆炸


@dataclass
class GaussianHMMParams:
    """拟合后冻结的 HMM 参数（月末重估后写入，供后续滤波复用）。"""

    startprob: np.ndarray  # (K,)
    transmat: np.ndarray  # (K, K)
    means: np.ndarray  # (K, D)
    covars: np.ndarray  # (K, D) 对角方差
    n_states: int
    n_features: int

    def to_jsonable(self) -> dict:
        """序列化为可入库的 JSON（float 列表）。"""
        return {
            "startprob": self.startprob.tolist(),
            "transmat": self.transmat.tolist(),
            "means": self.means.tolist(),
            "covars": self.covars.tolist(),
            "n_states": self.n_states,
            "n_features": self.n_features,
        }

    @classmethod
    def from_jsonable(cls, payload: dict) -> "GaussianHMMParams":
        """从入库 JSON 反序列化为参数对象。"""
        return cls(
            startprob=np.asarray(payload["startprob"], dtype=float),
            transmat=np.asarray(payload["transmat"], dtype=float),
            means=np.asarray(payload["means"], dtype=float),
            covars=np.asarray(payload["covars"], dtype=float),
            n_states=int(payload["n_states"]),
            n_features=int(payload["n_features"]),
        )


def _log_gaussian(x: np.ndarray, means: np.ndarray, covars: np.ndarray) -> np.ndarray:
    """逐状态计算对角高斯对数概率。

    Args:
        x: (T, D)
        means: (K, D)
        covars: (K, D) 对角方差
    Returns:
        (T, K) 每个观测在每个状态下的 log-likelihood
    """
    covars = np.maximum(covars, _MIN_VAR)
    # diff 形状为 观测数×状态数×特征数
    diff = x[:, None, :] - means[None, :, :]
    log_det = np.sum(np.log(covars), axis=1)
    quad = np.sum((diff**2) / covars[None, :, :], axis=2)
    d = x.shape[1]
    return -0.5 * (d * _LOG_2PI + log_det[None, :] + quad)


def _log_normalize(a: np.ndarray, axis: int = -1) -> tuple[np.ndarray, np.ndarray]:
    """返回 (归一化后的对数概率, logsumexp)。"""
    lse = _logsumexp(a, axis=axis, keepdims=True)
    return a - lse, np.squeeze(lse, axis=axis)


def _logsumexp(a: np.ndarray, axis: int = -1, keepdims: bool = False) -> np.ndarray:
    a_max = np.max(a, axis=axis, keepdims=True)
    a_max = np.where(np.isfinite(a_max), a_max, 0.0)
    out = np.log(np.sum(np.exp(a - a_max), axis=axis, keepdims=True)) + a_max
    if not keepdims:
        out = np.squeeze(out, axis=axis)
    return out


def _init_params(x: np.ndarray, n_states: int, seed: int) -> GaussianHMMParams:
    """确定性初始化：按第一维特征分位数把样本切成 K 组求 means/covars。"""
    rng = np.random.default_rng(seed)
    t, d = x.shape
    # 按综合排序键（各维之和）切分，保证初始状态有区分度
    order = np.argsort(x.sum(axis=1))
    means = np.zeros((n_states, d))
    covars = np.zeros((n_states, d))
    global_var = np.maximum(x.var(axis=0), _MIN_VAR)
    splits = np.array_split(order, n_states)
    for k, idx in enumerate(splits):
        if len(idx) == 0:
            means[k] = x.mean(axis=0) + rng.normal(0, 0.1, size=d)
            covars[k] = global_var
        else:
            means[k] = x[idx].mean(axis=0)
            covars[k] = np.maximum(x[idx].var(axis=0), global_var * 0.25)
    startprob = np.full(n_states, 1.0 / n_states)
    # 转移矩阵：对角占优（regime 有粘性）
    transmat = np.full((n_states, n_states), 0.1 / max(n_states - 1, 1))
    np.fill_diagonal(transmat, 0.9)
    transmat /= transmat.sum(axis=1, keepdims=True)
    return GaussianHMMParams(startprob, transmat, means, covars, n_states, d)


def _forward_backward(
    log_startprob: np.ndarray,
    log_transmat: np.ndarray,
    framelogprob: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """对数域前向-后向。返回 (log_alpha, log_beta, log_xi_sum, loglik)。"""
    t, k = framelogprob.shape
    log_alpha = np.zeros((t, k))
    log_beta = np.zeros((t, k))

    log_alpha[0] = log_startprob + framelogprob[0]
    for i in range(1, t):
        log_alpha[i] = (
            _logsumexp(log_alpha[i - 1][:, None] + log_transmat, axis=0)
            + framelogprob[i]
        )

    log_beta[t - 1] = 0.0
    for i in range(t - 2, -1, -1):
        log_beta[i] = _logsumexp(
            log_transmat + framelogprob[i + 1][None, :] + log_beta[i + 1][None, :],
            axis=1,
        )

    loglik = _logsumexp(log_alpha[t - 1], axis=0)

    # xi 求和：sum_t P(state_i at t, state_j at t+1 | x)
    log_xi_sum = np.full((k, k), -np.inf)
    for i in range(t - 1):
        log_xi = (
            log_alpha[i][:, None]
            + log_transmat
            + framelogprob[i + 1][None, :]
            + log_beta[i + 1][None, :]
            - loglik
        )
        log_xi_sum = np.logaddexp(log_xi_sum, log_xi)

    return log_alpha, log_beta, log_xi_sum, float(loglik)


def fit_gaussian_hmm(
    x: np.ndarray,
    n_states: int = 3,
    n_iter: int = 100,
    tol: float = 1e-4,
    seed: int = 42,
) -> GaussianHMMParams:
    """用 Baum-Welch 拟合高斯 HMM。

    Args:
        x: (T, D) 标准化后的特征矩阵
        n_states: 隐状态数（默认 3：逐利/观望/避险）
        n_iter: 最大 EM 迭代
        tol: 收敛阈值（相邻迭代 loglik 增量）
        seed: 初始化随机种子，保证可复现
    """
    x = np.asarray(x, dtype=float)
    if x.ndim != 2:
        raise ValueError("x 必须是二维 (T, D)")
    if x.shape[0] < n_states:
        raise ValueError("样本数不足以拟合该状态数")

    params = _init_params(x, n_states, seed)
    prev_loglik = -np.inf

    for _ in range(n_iter):
        framelogprob = _log_gaussian(x, params.means, params.covars)
        log_startprob = np.log(np.clip(params.startprob, 1e-12, None))
        log_transmat = np.log(np.clip(params.transmat, 1e-12, None))

        log_alpha, log_beta, log_xi_sum, loglik = _forward_backward(
            log_startprob, log_transmat, framelogprob
        )

        # gamma: 后验 P(state | x)（平滑，仅用于 M-step 参数估计）
        log_gamma, _ = _log_normalize(log_alpha + log_beta, axis=1)
        gamma = np.exp(log_gamma)  # (T, K)

        # M-step
        startprob = gamma[0] + 1e-12
        startprob /= startprob.sum()

        xi_sum = np.exp(log_xi_sum)
        transmat = xi_sum + 1e-12
        transmat /= transmat.sum(axis=1, keepdims=True)

        weights = gamma.sum(axis=0)  # (K,)
        means = (gamma.T @ x) / weights[:, None]
        covars = np.zeros_like(params.covars)
        for k in range(n_states):
            diff = x - means[k]
            covars[k] = (gamma[:, k][:, None] * diff**2).sum(axis=0) / weights[k]
        covars = np.maximum(covars, _MIN_VAR)

        params = GaussianHMMParams(
            startprob, transmat, means, covars, n_states, x.shape[1]
        )

        if loglik - prev_loglik < tol and prev_loglik != -np.inf:
            break
        prev_loglik = loglik

    return params


def filter_posteriors(params: GaussianHMMParams, x: np.ndarray) -> np.ndarray:
    """前向滤波后验 P(state_t | x_1..x_t)（**不回改**：只看当天及之前）。

    这是对外用于给每日打标签的后验：第 t 行只依赖前 t 个观测，
    追加未来数据不会改写历史行，满足「状态序列不回改」。

    Returns:
        (T, K) 每天的滤波后验（每行和为 1）
    """
    x = np.asarray(x, dtype=float)
    framelogprob = _log_gaussian(x, params.means, params.covars)
    log_startprob = np.log(np.clip(params.startprob, 1e-12, None))
    log_transmat = np.log(np.clip(params.transmat, 1e-12, None))

    t, k = framelogprob.shape
    log_alpha = np.zeros((t, k))
    posteriors = np.zeros((t, k))

    log_alpha[0], _ = _log_normalize(log_startprob + framelogprob[0], axis=0)
    posteriors[0] = np.exp(log_alpha[0])
    for i in range(1, t):
        pred = _logsumexp(log_alpha[i - 1][:, None] + log_transmat, axis=0)
        log_alpha[i], _ = _log_normalize(pred + framelogprob[i], axis=0)
        posteriors[i] = np.exp(log_alpha[i])

    return posteriors
