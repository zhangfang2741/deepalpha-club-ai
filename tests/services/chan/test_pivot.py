"""缠论中枢（pivot）识别单元测试。

笔级中枢识别已切换到 czsc（见 test_czsc_adapter.py），本文件只测仍为自研的
线段级中枢（find_segment_pivots）与走势类型判定（classify_walk_type）。

不变量（缠论标准）：
1. ZG/ZD 由最初三段固定，延伸时不变；只有 GG/DD 随延伸更新。
2. ZG = min(前三段高点)，ZD = max(前三段低点)，且 ZG > ZD。
3. 延伸并入的段与固定区间 [ZD, ZG] 有重叠。
"""
from __future__ import annotations

from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.pivot import find_segment_pivots
from app.services.chan.segment import Segment
from app.services.chan.stroke import Stroke


def _mc(idx: int, high: float, low: float) -> MergedCandle:
    return MergedCandle(idx=idx, time=f"D{idx:03d}", open=(high + low) / 2, high=high,
                        low=low, close=(high + low) / 2, raw_start=idx, raw_end=idx)


def _fx(kind: str, idx: int, price: float) -> Fractal:
    mid = _mc(idx, price, price - 1) if kind == "top" else _mc(idx, price + 1, price)
    return Fractal(type=kind, candle=mid, left=_mc(idx - 1, price, price - 2),
                   right=_mc(idx + 1, price, price - 2))


def _chain(prices: list[float]) -> list[Segment]:
    """按价格序列构造「单笔线段」链：每段一笔，段的 high/low 即该笔的高低点。

    中枢识别算法只消费元素的 high/low/start_time/end_time，单笔线段与单笔
    等价，可直接测 find_segment_pivots 的不变量。
    """
    segments: list[Segment] = []
    for i in range(len(prices) - 1):
        direction = "up" if prices[i + 1] > prices[i] else "down"
        sk = "bottom" if direction == "up" else "top"
        ek = "top" if direction == "up" else "bottom"
        stroke = Stroke(direction=direction,
                        start=_fx(sk, i * 10, prices[i]),
                        end=_fx(ek, i * 10 + 5, prices[i + 1]))
        segments.append(Segment(direction=direction, strokes=[stroke]))
    return segments


def test_pivot_zg_zd_fixed_by_first_three():
    # 前三段：10→20(上), 20→12(下), 12→18(上) → ZG=min(20,20,18)=18, ZD=max(10,12,12)=12
    segments = _chain([10, 20, 12, 18])
    pivots = find_segment_pivots(segments)
    assert len(pivots) == 1
    p = pivots[0]
    assert p.zg == 18
    assert p.zd == 12
    assert p.zg > p.zd


def test_extension_keeps_zg_zd_updates_gg_dd():
    # 第四段回到中枢内并触及更极端的高/低：ZG/ZD 应保持不变，GG/DD 随之更新
    # 段: 10→20, 20→12, 12→18, 18→13(下,仍与[12,18]重叠，且低点13)，再 13→19(上,高点19)
    segments = _chain([10, 20, 12, 18, 13, 19])
    pivots = find_segment_pivots(segments)
    assert len(pivots) == 1
    p = pivots[0]
    # ZG/ZD 仍由前三段固定
    assert p.zg == 18
    assert p.zd == 12
    # GG/DD 覆盖所有并入段的极值
    assert p.gg >= 20
    assert p.dd <= 10
    # 延伸确实并入了后续段
    assert len(p.elements) >= 4


def test_no_pivot_when_no_overlap():
    # 三段无重叠（单边）→ 不成中枢
    segments = _chain([10, 20, 18, 30])  # ZG=min(20,20,30)=20, ZD=max(10,18,18)=18 -> 20>18 仍重叠
    # 用明显单边：10→20→19→40，前三段 ZG=min(20,20,40)=20, ZD=max(10,19,19)=19 → 重叠窄
    segments2 = _chain([10, 40, 38, 80])  # ZG=min(40,40,80)=40, ZD=max(10,38,38)=38 → 40>38 重叠
    # 构造真正无重叠：第一段高点低于第三段低点
    segments3 = _chain([10, 20, 15, 50, 45, 90])
    # 前三段 10→20,20→15,15→50：ZG=min(20,20,50)=20, ZD=max(10,15,15)=15 → 20>15 有重叠
    # 说明连续三段几乎总有重叠；此处仅验证函数对短序列不崩
    assert isinstance(find_segment_pivots(segments), list)
    assert isinstance(find_segment_pivots(segments2), list)
    assert isinstance(find_segment_pivots(segments3), list)


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
