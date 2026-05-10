"""ETF 服务模块。

提供 ETF 数据获取、资金流计算和热力图构建功能。
"""

from .calculator import compute_clv, compute_flow, date_label, z_score_normalize
from .constants import CHINESE_NAMES, ETF_LIBRARY, TRACKED_ETFS
from .fetcher import (
    build_heatmap_data,
    fetch_candles,
    fetch_etf_flows,
    fetch_etf_list_summary,
)

__all__ = [
    # 计算函数
    "compute_clv",
    "compute_flow",
    "date_label",
    "z_score_normalize",
    # 常量
    "CHINESE_NAMES",
    "ETF_LIBRARY",
    "TRACKED_ETFS",
    # 数据获取
    "build_heatmap_data",
    "fetch_candles",
    "fetch_etf_flows",
    "fetch_etf_list_summary",
]
