"""缠论买卖点信号回归测试（真实数据端到端）。

用真实标的 FIG（Figma，2025-07 上市）的日线复权数据锁定一个关键回归：
从 ~122 一路跌到 ~50 的底部背驰，必须能识别出「一买」——曾因过度收紧
（一买仅趋势背驰触发 + 过严的趋势/盘整判据）被整段抹掉。
"""
from __future__ import annotations

from app.services.chan.analyzer import ChanAnalyzer

# FIG 前复权 OHLC（时间升序，2025-07-31 上市首日起 30 个交易日）
_FIG_OHLC = [
    (85, 124.63, 84.11, 115.5), (134.82, 142.92, 110.11, 122), (113.92, 114.29, 88.6, 88.6),
    (91.19, 94, 79, 79.08), (76.9, 91.49, 76.65, 90.32), (86.65, 87.88, 77.8, 78.24),
    (82.54, 82.6, 78, 78.11), (78.78, 84, 78, 82.5), (84, 90.69, 83.91, 87.36),
    (90.96, 91, 81.05, 81.91), (81.5, 82.94, 76, 76.31), (79, 81, 76.56, 79.42),
    (79.2, 80.75, 75.5, 76.16), (76.42, 76.57, 68.61, 69.41), (70, 75.15, 67, 74.04),
    (73.1, 74.07, 71.82, 72.76), (73.41, 78, 72.41, 77.3), (74.56, 75.7, 69.61, 70.4),
    (70.88, 72.2, 69.3, 70.13), (70.5, 71.68, 68.52, 69.88), (70.18, 72.11, 69.31, 71.26),
    (70.51, 71.44, 68.9, 70.28), (68.96, 68.96, 64.55, 65.57), (66.7, 68.59, 65.54, 68.13),
    (55.9, 57.35, 53.2, 54.56), (52.38, 54.96, 50.49, 54.86), (54.17, 55.32, 52.4, 52.47),
    (52.45, 53.62, 51.43, 53.32), (53.61, 55.21, 50.82, 51.06), (51.05, 56.32, 51.04, 55.96),
]


def _fig_bars() -> list[dict]:
    return [
        {"time": f"2025-{(i // 20) + 8:02d}-{(i % 20) + 1:02d}",
         "open": o, "high": h, "low": low, "close": c, "volume": 1000}
        for i, (o, h, low, c) in enumerate(_FIG_OHLC)
    ]


def test_fig_bottom_divergence_yields_buy1():
    """FIG 底部背驰应产出一买（回归：过度收紧曾把它整段抹掉）。"""
    result = ChanAnalyzer().analyze("FIG", _fig_bars())
    buy1 = [s for s in result.signals if s.type == "buy1"]
    assert buy1, "FIG 底部背驰应至少产出一个一买信号"
    # 一买应落在跌势末端的低位（远低于起始的百元上方）
    assert min(s.price for s in buy1) < 60


def test_fig_structure_invariants():
    """FIG 上笔首尾相连、方向交替、线段不吞没起点。"""
    result = ChanAnalyzer().analyze("FIG", _fig_bars())
    st = result.strokes
    for a, b in zip(st, st[1:], strict=False):
        assert a.end is b.start
        assert a.direction != b.direction
    for seg in result.segments:
        origin = seg.strokes[0].start_price
        if seg.direction == "up":
            assert seg.low >= origin - 1e-6
        else:
            assert seg.high <= origin + 1e-6
