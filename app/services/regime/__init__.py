"""市场状态监控（regime）服务模块。

三层逻辑：
1. 信号层：三篮子 RS → 合成 ODS / CF（滚动窗口）+ 真实 OBV/CMF 量价确认。
2. 状态层：[纳指收益, 已实现波动, VIX, ODS, CF] 喂真拟合 HMM，输出逐利/观望/避险后验。
3. 应用层：后验（1−p_避险）写因子表 regime_features 做动态加权。
"""

from app.services.regime.pipeline import (
    RegimeDailyRecord,
    compute_regime_from_market,
    persist_records,
    run_regime_stage,
)

__all__ = [
    "RegimeDailyRecord",
    "compute_regime_from_market",
    "persist_records",
    "run_regime_stage",
]
