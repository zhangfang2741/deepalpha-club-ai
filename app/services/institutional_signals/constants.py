"""机构资金信号常量：维度元数据、权重与打分阈值。"""

# 维度元数据（key -> 中文名 + 核心问题），顺序即机构决策链顺序
DIMENSION_META = {
    "expectation": ("预期", "分析师是不是开始重新定价未来？"),
    "positioning": ("仓位", "资金是不是已经开始下注？"),
    "participation": ("参与度", "其他资金开始跟了吗？"),
    "fundamental": ("基本面", "企业经营有没有真正改善？"),
    "confirmation": ("确认", "长期资金确认了吗？"),
}

# 综合分权重（未实现的维度按 unavailable 处理，权重动态归一化）
DIMENSION_WEIGHTS = {
    "expectation": 0.30,
    "positioning": 0.25,
    "participation": 0.20,
    "fundamental": 0.15,
    "confirmation": 0.10,
}

# ── Participation 阈值 ──────────────────────────────────────────────────────
RELVOL_STRONG = 2.0      # 相对成交量 ≥ 2.0 视为显著放量
RELVOL_ELEVATED = 1.5
RELVOL_MILD = 1.2
RELVOL_QUIET = 0.8       # < 0.8 视为缩量
GAP_PCT = 2.0            # 跳空阈值（%）
VOLUME_LOOKBACK = 20     # 相对成交量与突破的回看窗口（交易日）

# ── Expectation 阈值 ────────────────────────────────────────────────────────
TP_STRONG_PCT = 5.0      # 目标价环比涨幅 ≥ 5% 视为强上调
TP_MILD_PCT = 1.0
MIN_ANALYST_COUNT = 2    # 目标价样本数下限，低于此不采信
BUY_RATIO_MAJORITY = 0.6  # 买入评级占比 ≥ 0.6 视为共识偏多

# ── Positioning 阈值（yfinance 期权快照）────────────────────────────────────
# 快照可算实的量：Put/Call 比、Call 量/仓比、ATM IV 水平。
# 真正的 OI 变化 / IV Rank 需每日快照库（后续基建）。
PCR_CALL_HEAVY = 0.7     # Put/Call 成交量比 ≤ 0.7 视为显著看涨下注
PCR_MILD_CALL = 0.9
PCR_PUT_HEAVY = 1.3      # ≥ 1.3 视为看跌/避险主导
CALL_VOL_OI_FRESH = 0.4  # Call 当日成交量 / Call OI ≥ 0.4 视为新增下注活跃
IV_ELEVATED = 0.60       # ATM 年化 IV ≥ 60% 视为偏高（事件预期）
IV_MILD = 0.40
OPTION_EXPIRY_MAX_DAYS = 45  # 只聚合 45 天内的近月合约
OPTION_EXPIRY_MIN_COUNT = 2  # 至少聚合最近 2 个到期日
