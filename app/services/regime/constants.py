"""市场状态监控（regime）模块常量。

三篮子（对应「资金像水，逐利/避险」直觉）：
- OFFENSE 进攻篮子：科技/半导体/可选消费/工业 —— 逐利时资金涌入。
- DEFENSE 防御篮子：公用事业/必需消费/医疗 —— 避险时资金流入。
- CASH 现金篮子：短端国债 ETF —— 整体离场时资金停泊。
"""
from __future__ import annotations

# 三篮子成分（等权）
OFFENSE_BASKET: list[str] = ["XLK", "XLY", "XLI", "SMH"]
DEFENSE_BASKET: list[str] = ["XLU", "XLP", "XLV"]
CASH_BASKET: list[str] = ["BIL", "SHV"]

# 纳指与波动率代理
NASDAQ_SYMBOL = "QQQ"
VIX_SYMBOL = "^VIX"

# 滚动窗口参数（统一用滚动窗口，不用 rebase-since-基准日）
RS_WINDOW = 20  # 篮子相对强弱回看窗口（交易日）
RETURN_WINDOW = 20  # 纳指动量窗口
VOL_WINDOW = 20  # 已实现波动窗口
OBV_CMF_WINDOW = 20  # OBV 斜率 / CMF 窗口

TRADING_DAYS = 252  # 年化因子

# HMM 状态与标签
N_STATES = 3
LABEL_RISK_ON = "risk_on"  # 逐利
LABEL_NEUTRAL = "neutral"  # 观望
LABEL_RISK_OFF = "risk_off"  # 避险

STATE_LABELS = [LABEL_RISK_ON, LABEL_NEUTRAL, LABEL_RISK_OFF]

LABEL_ZH = {
    LABEL_RISK_ON: "逐利",
    LABEL_NEUTRAL: "观望",
    LABEL_RISK_OFF: "避险",
}

# 拟合所需最小历史（交易日）——不足则不产出状态标签，避免小样本乱拟合
MIN_FIT_HISTORY = 252

# 「持续 N 日」标签：连续处于同一 regime 达到该天数才算确认
PERSIST_N_DAYS = 3

# 后验退火参数：抑制高斯 HMM 滤波后验饱和成硬 0/1，让 factor_weight 成为平滑旋钮。
# 直觉：对角高斯假设 5 个特征相互独立，但 ODS/波动/VIX 日频高度自相关，
# 5 维似然连乘会把「其实约 1 份独立证据」当成 5 份，后验被压成硬 0/1。
# 温度 T 把每日发射证据退火回约 1 维量级，收缩+转移封顶进一步抑制过度自信。
COVAR_SHRINKAGE = 0.35  # 协方差向池化方差收缩系数 λ
MAX_SELF_TRANSITION = 0.90  # 自转移概率上限，掐断逐日复利式钉死
POSTERIOR_TEMPERATURE = 6.0  # 发射对数似然退火温度 T（≥1）
