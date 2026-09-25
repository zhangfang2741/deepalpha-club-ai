"""缠论线段（segment）识别单元测试。

不变量：
1. 线段至少由3笔构成，方向由第一笔决定，内部笔为该段的连续子序列。
2. 线段不得吞没「收复其起点」的反向走势（下降线段不能包含创出新高的一段）。
3. 识别使用索引而非 dataclass 值相等，避免同值笔互相误匹配。
"""
from __future__ import annotations

from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.segment import find_segments
from app.services.chan.stroke import Stroke


def _mc(idx: int, high: float, low: float) -> MergedCandle:
    return MergedCandle(idx=idx, time=f"D{idx:03d}", open=(high + low) / 2, high=high,
                        low=low, close=(high + low) / 2, raw_start=idx, raw_end=idx)


def _fx(kind: str, idx: int, price: float) -> Fractal:
    # Fractal.price 顶取 candle.high、底取 candle.low，构造时让其正好等于 price
    if kind == "top":
        mid = _mc(idx, high=price, low=price - 1)
    else:
        mid = _mc(idx, high=price + 1, low=price)
    return Fractal(type=kind, candle=mid, left=_mc(idx - 1, price, price - 2),
                   right=_mc(idx + 1, price, price - 2))


def _stroke(direction: str, idx: int, start_price: float, end_price: float) -> Stroke:
    start_kind = "bottom" if direction == "up" else "top"
    end_kind = "top" if direction == "up" else "bottom"
    return Stroke(
        direction=direction,
        start=_fx(start_kind, idx * 10, start_price),
        end=_fx(end_kind, idx * 10 + 5, end_price),
    )


def _chain(prices: list[float]) -> list[Stroke]:
    """由一串转折价构造首尾相连、方向交替的笔序列。"""
    strokes: list[Stroke] = []
    for i in range(len(prices) - 1):
        direction = "up" if prices[i + 1] > prices[i] else "down"
        strokes.append(_stroke(direction, i, prices[i], prices[i + 1]))
    return strokes


def test_up_segment_three_strokes():
    # 100->130->115->140：一条上升线段（3笔）
    strokes = _chain([100, 130, 115, 140])
    segs = find_segments(strokes)
    assert len(segs) == 1
    assert segs[0].direction == "up"
    assert segs[0].stroke_count == 3
    assert segs[0].start_price == 100
    assert segs[0].end_price == 140


def test_segment_not_swallow_new_high():
    # 130->114->125->109->140->119：
    # 前3笔构成下降线段(130->109)，随后 109->140 收复并突破起点130，
    # 下降线段必须结束，不能把创出新高(140>130)的一段吞进来。
    strokes = _chain([130, 114, 125, 109, 140, 119])
    segs = find_segments(strokes)
    assert segs, "应至少识别出一条下降线段"
    down = segs[0]
    assert down.direction == "down"
    # 该下降线段的最高点不得超过其起点 130（未吞没创新高走势）
    assert down.high <= 130 + 1e-9
    assert down.end_price <= 130


def test_segment_strokes_are_contiguous_subsequence():
    strokes = _chain([100, 130, 115, 140, 120, 150, 130, 160])
    segs = find_segments(strokes)
    assert segs
    for seg in segs:
        # 段内笔在原序列中连续
        first = strokes.index(seg.strokes[0])
        for offset, s in enumerate(seg.strokes):
            assert strokes[first + offset] is s
        assert seg.stroke_count >= 3


def test_establishment_retrace_must_not_reclaim_origin():
    # 回归：线段确立阶段的第一个回调笔若已收复起点，则该处不成线段，
    # 不得把「越过自身起点」的走势并入线段（模糊测试曾在此暴露 I8 违反）。
    # 100->80(下) ->105(上,越过起点100) ->70(下) ->110(上) ->60(下)
    strokes = _chain([100, 80, 105, 70, 110, 60])
    for seg in find_segments(strokes):
        origin = seg.strokes[0].start_price
        if seg.direction == "up":
            assert seg.low >= origin - 1e-6, "上升线段最低不得跌破起点"
        else:
            assert seg.high <= origin + 1e-6, "下降线段最高不得越过起点"


def test_no_segment_high_exceeds_origin_general():
    # 综合：任意构造下，每条线段都不得吞没自身起点
    for prices in (
        [100, 130, 115, 140, 118, 160, 150, 170],
        [200, 170, 190, 150, 175, 120],
        [50, 62, 48, 70, 55, 80, 60, 95],
    ):
        for seg in find_segments(_chain(prices)):
            origin = seg.strokes[0].start_price
            if seg.direction == "up":
                assert seg.low >= origin - 1e-6
            else:
                assert seg.high <= origin + 1e-6


def test_adjacent_segments_alternate_direction():
    # 线段必须严格交替：确立失败跳过若干笔后，不得误起一条同向线段
    for prices in (
        [100, 130, 115, 140, 118, 160, 150, 170, 120, 175, 130, 190],
        [200, 150, 175, 120, 160, 90, 130, 70, 110, 50],
        [50, 80, 60, 95, 70, 62, 90, 55, 100, 75, 130],
    ):
        strokes = _chain(prices)
        segs = find_segments(strokes)
        for a, b in zip(segs, segs[1:], strict=False):
            if _connected(strokes, a, b):
                assert a.direction != b.direction, "首尾相接的线段方向必须交替"


def test_gap_second_case_keeps_one_segment():
    # 第二种情况：上升途中一笔回抽创出较低高点(155<160)且与上一回调间有缺口，
    # 但随后突破到新高(180)——缺口是中继，应保持为【一条】上升线段，而非在 160 处误分。
    strokes = _chain([100, 140, 125, 160, 150, 155, 130, 180])
    segs = find_segments(strokes)
    assert len(segs) == 1
    assert segs[0].direction == "up"
    assert segs[0].start_price == 100
    assert segs[0].end_price == 180
    assert segs[0].stroke_count == 7


def test_gap_second_case_down_direction():
    # 对称的下降第二种情况：跌途中一笔反抽较高低点且带缺口，随后跌破新低。
    strokes = _chain([180, 130, 145, 120, 128, 125, 150, 100])
    segs = find_segments(strokes)
    assert segs
    assert segs[0].direction == "down"
    assert segs[0].start_price == 180
    assert segs[0].end_price == 100


def test_too_few_strokes():
    assert find_segments([]) == []
    assert find_segments(_chain([100, 120])) == []  # 仅1笔


def _assert_invariants(strokes: list[Stroke], segs) -> None:
    pos = {id(s): k for k, s in enumerate(strokes)}
    for seg in segs:
        first = pos[id(seg.strokes[0])]
        for offset, s in enumerate(seg.strokes):
            assert strokes[first + offset] is s
        assert seg.stroke_count >= 3
        assert seg.direction == seg.strokes[0].direction
        origin = seg.strokes[0].start_price
        if seg.direction == "up":
            assert seg.low >= origin - 1e-6
        else:
            assert seg.high <= origin + 1e-6
    for a, b in zip(segs, segs[1:], strict=False):
        if _connected(strokes, a, b):  # 首尾相接的必须交替；隔着空档的按实际走势
            assert a.direction != b.direction


def _connected(strokes: list[Stroke], a, b) -> bool:
    pos = {id(s): k for k, s in enumerate(strokes)}
    return pos[id(a.strokes[-1])] + 1 == pos[id(b.strokes[0])]


def test_segments_connect_end_to_start_in_consolidation():
    # 上升段 100->140 结束后进入震荡：三笔重叠即成下降段，不要求第三笔创新低；
    # 线段首尾相接，前一段终点 = 下一段起点，中间不留没被划入线段的笔。
    strokes = _chain([100, 130, 115, 140, 120, 135, 118, 132, 110, 150, 125, 160, 130, 150, 120])
    segs = find_segments(strokes)
    _assert_invariants(strokes, segs)
    assert len(segs) >= 2
    for a, b in zip(segs, segs[1:], strict=False):
        assert _connected(strokes, a, b), "相邻线段必须首尾相接"


def test_first_case_fractal_ends_segment_and_next_starts_there():
    # 特征序列 (130,115)(140,125)(135,120) 在 140 处形成第一种情况顶分型：上升段在 140
    # 结束（不能因为之后涨到 160 就硬并成一段）；下降段 140->125->135->120 从 140 接上，
    # 其后 160 收复下降段起点，下降段结束，上升段再从 120 接上。
    strokes = _chain([100, 130, 115, 140, 125, 135, 120, 160, 150, 170, 140, 155, 130])
    segs = find_segments(strokes)
    _assert_invariants(strokes, segs)
    assert (segs[0].direction, segs[0].start_price, segs[0].end_price) == ("up", 100, 140)
    assert (segs[1].direction, segs[1].start_price, segs[1].end_price) == ("down", 140, 120)
    for a, b in zip(segs, segs[1:], strict=False):
        assert _connected(strokes, a, b)


def test_random_walks_only_break_where_no_valid_segment_exists():
    """随机走势：不变量零违反，空档处必然构不成线段。

    相邻线段之间若有空档，从前段终点起步的线段必然不成立（不足三笔即被收复起点，或只是「一笔 + 横盘」）——不为了连起来而连起来。
    """
    import random

    from app.services.chan.segment import _extreme_on_first, _segment_end

    rng = random.Random(7)
    pairs = gaps = 0
    for _ in range(2000):
        prices = [100.0]
        for k in range(rng.randint(6, 40)):
            step = rng.uniform(3, 30)
            prices.append(prices[-1] + (step if k % 2 == 0 else -step))
        strokes = _chain(prices)
        pos = {id(s): k for k, s in enumerate(strokes)}
        segs = find_segments(strokes)
        _assert_invariants(strokes, segs)
        for a, b in zip(segs, segs[1:], strict=False):
            pairs += 1
            if _connected(strokes, a, b):
                continue
            gaps += 1
            i = pos[id(a.strokes[-1])] + 1
            d = strokes[i].direction
            end = _segment_end(strokes, i, d)
            assert end is None or end < i + 2 or _extreme_on_first(strokes, i, end, d)
    assert gaps / pairs < 0.15


def test_origin_reclaimed_segment_ends_at_its_extreme():
    # 真实回归（NVDA 2024-11~2025-01）：下降段 149.37->131.46->146.17->126.53->141.54->133.48，
    # 随后 152.74 收复起点。下降段必须结束在段内最低 126.53，而不是触发前一笔 133.48；
    # 126.53->141.54->133.48->152.74 接着构成上升段。
    strokes = _chain([144.04, 131.76, 149.37, 131.46, 146.17, 126.53, 141.54, 133.48,
                      152.74, 129.18, 148.58, 112.72])
    segs = find_segments(strokes)
    _assert_invariants(strokes, segs)
    down = next(s for s in segs if s.direction == "down")
    assert down.start_price == 149.37
    assert down.end_price == 126.53


def test_confirmed_segments_end_at_their_extreme():
    """已结束的线段终点应是段内极值。

    唯一例外（约 0.1%）：线段极值就在首笔终点、此后高点逐级走低的横盘——特征序列
    分型的第一元素须在极值之前，此处不存在，分型无法按定义成立。容忍 0.5% 以内。
    """
    import random

    rng = random.Random(11)
    total = bad = 0
    for _ in range(2000):
        prices = [100.0]
        for k in range(rng.randint(6, 40)):
            step = rng.uniform(3, 30)
            prices.append(prices[-1] + (step if k % 2 == 0 else -step))
        strokes = _chain(prices)
        segs = find_segments(strokes)
        _assert_invariants(strokes, segs)
        for seg in segs[:-1]:  # 最后一段可能未走完
            total += 1
            ends = [s.end_price for s in seg.strokes if s.direction == seg.direction]
            bad += seg.end_price != (max(ends) if seg.direction == "up" else min(ends))
    assert bad / total < 0.005


def test_float_noise_high_is_not_a_new_extreme():
    # 真实回归（腾讯 2024-11~12）：前复权价 422.3494536 与 422.3494581 仅差浮点尾差，
    # 不算创新高；384->422->394->422 只是「一笔 + 横盘」，下降段应一直走到 357.48。
    strokes = _chain([357.67, 472.72, 396.48, 427.25, 384.13, 422.3494536, 393.74,
                      422.3494581, 357.48, 511.52, 463.70, 536.02, 489.18, 534.06, 410.59])
    segs = find_segments(strokes)
    _assert_invariants(strokes, segs)
    down = next(s for s in segs if s.direction == "down")
    assert (down.start_price, down.end_price) == (472.72, 357.48)


def test_failed_reversal_revives_previous_segment():
    # 真实回归（9999.HK 2026-01~07）：下降段 232.02->168.99 后，短上升段 168.99->186.97
    # 刚成形就被一笔创新低（168.59 < 168.99）破坏——这是失败的反转，原下降段并未结束：
    # 应为下降段 232.02->168.59、上升段从 168.59 接上，不能在 186.97->168.59 留空档。
    strokes = _chain([150, 200, 180, 232.02, 173.76, 190.22, 168.99, 182.57, 172.98, 186.97,
                      168.59, 198.35, 185.11, 202.50, 180.11, 216.49, 186.01, 210.49, 190.00])
    segs = find_segments(strokes)
    _assert_invariants(strokes, segs)
    down = next(s for s in segs if s.direction == "down")
    assert (down.start_price, down.end_price) == (232.02, 168.59)
    for a, b in zip(segs, segs[1:], strict=False):
        assert _connected(strokes, a, b), "失败的反转不应留下空档"
