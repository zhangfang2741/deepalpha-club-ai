"""走势类型判定（classify_walk_type）单元测试。

中枢识别全部来自 czsc（见 test_czsc_adapter.py），不再有自研线段级中枢。
"""
from __future__ import annotations


def _pivot(zg: float, zd: float) -> "object":
    from app.services.chan.pivot import Pivot
    return Pivot(zg=zg, zd=zd, gg=zg + 1, dd=zd - 1, start_time="", end_time="",
                level="stroke", elements=[])


def test_classify_walk_type():
    from app.services.chan.pivot import classify_walk_type
    assert classify_walk_type([]) == "none"
    assert classify_walk_type([_pivot(20, 10)]) == "consolidation"
    # 中枢依次抬高（后中枢 ZD > 前中枢 ZG）→ 上涨趋势
    assert classify_walk_type([_pivot(20, 10), _pivot(40, 25)]) == "up_trend"
    # 中枢依次降低 → 下跌趋势
    assert classify_walk_type([_pivot(40, 25), _pivot(20, 10)]) == "down_trend"
    # 中枢区间重叠 → 盘整
    assert classify_walk_type([_pivot(20, 10), _pivot(22, 12)]) == "consolidation"
