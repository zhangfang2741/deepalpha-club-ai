"""多空倾向的因子权重与判定阈值。

单独成文件是为了让权重只有一处定义：`narrative.py` 负责量价那一项、
`analyzer.py` 负责其余各项，两边都从这里取值，口径才不会各自漂移
（analyzer 已 import narrative，反向导入会成环）。

约定：分数为正表示偏多、为负表示偏空、0 表示中性。
"""
from __future__ import annotations

from dataclasses import dataclass

# ---- 各维度权重（绝对值，方向由调用方定符号）----
SIGNAL_WEIGHT = {"strong": 2.5, "medium": 2.0, "weak": 1.5}
# 未确认信号落在最后一笔上，属左侧预判，权重打折
UNCONFIRMED_DISCOUNT = 0.6
STROKE_WEIGHT = 1.0      # 末笔方向：级别最小，权重最低
SEGMENT_WEIGHT = 1.5     # 线段方向：大级别趋势，权重高于笔
PIVOT_WEIGHT = 1.5       # 相对中枢的位置：多空争夺区的胜负手
DIVERGENCE_WEIGHT = 1.5  # 背驰：只削弱当前方向的力度，不单独定方向
VOLUME_WEIGHT = 0.5      # 量价配合：佐证性质，权重最低

# 加权总分低于此绝对值视为多空僵持
BIAS_THRESHOLD = 1.5
# 超过此绝对值，措辞从「略偏强/弱」升级为「偏强/弱」
STRONG_BIAS_THRESHOLD = 3.5


@dataclass
class BiasFactor:
    """单个技术因子对多空倾向的贡献。

    把每条依据的方向和权重显式记下来，结论才能与依据同源。改造前 bias 只看
    「末笔方向 × 背驰」，于是页面上出现过 chip 写「偏空」、而下方依据写着
    「多头占优、大级别趋势偏多」的自相矛盾。
    """
    text: str      # 展示给用户的那句依据
    score: float   # 正=偏多，负=偏空，0=中性


def score_to_bias(score: float) -> str:
    """加权总分 → bullish / bearish / neutral。"""
    if score >= BIAS_THRESHOLD:
        return "bullish"
    if score <= -BIAS_THRESHOLD:
        return "bearish"
    return "neutral"
