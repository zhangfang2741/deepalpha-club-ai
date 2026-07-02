"""缠论最右侧结构“未确认”标注单元测试。

验证分型 / 笔 / 线段 / 中枢 / 信号在最右侧尚未被后续K线确认时，
会被正确标注为 confirmed=False，并汇总到 pending_notes。
"""
from __future__ import annotations

from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.fractal import find_fractals, merge_candles


def _bar(t: str, o: float, h: float, low: float, c: float, v: float = 1000) -> dict:
    return {"time": t, "open": o, "high": h, "low": low, "close": c, "volume": v}


def _zigzag_bars() -> list[dict]:
    """构造一段上下震荡的K线，足以形成多笔/中枢/信号，方便检验确认标注。"""
    # 锯齿形：低-高-低-高……每个转折之间留足够K线（>=5）以成笔
    pivots = [10, 30, 15, 35, 18, 40, 20, 45, 22, 48]
    bars: list[dict] = []
    day = 0
    prev = pivots[0]
    for target in pivots[1:]:
        step = (target - prev) / 6.0
        for _ in range(6):
            day += 1
            nxt = prev + step
            o, c = prev, nxt
            h = max(o, c) + 0.5
            low = min(o, c) - 0.5
            bars.append(_bar(f"2024-{(day // 28) + 1:02d}-{(day % 28) + 1:02d}", o, h, low, c))
            prev = nxt
    return bars


def test_last_fractal_is_unconfirmed():
    """最右侧分型的右侧K线是最后一根合并K线时，应标注为未确认。"""
    bars = _zigzag_bars()
    merged = merge_candles(bars)
    fractals = find_fractals(merged)
    assert fractals  # 至少要有分型

    analyzer = ChanAnalyzer()
    result = analyzer.analyze("TEST", bars)

    # 结果中的分型经过确认标注：非最后的分型应当确认，最后一个若贴近右侧则未确认
    if result.fractals:
        last = result.fractals[-1]
        last_mc_idx = len(result.merged_candles) - 1
        expected = (last.idx + 1) < last_mc_idx
        assert last.confirmed == expected


def test_last_stroke_unconfirmed():
    """最后一笔（右侧前沿）必须为未确认，之前的笔已确认。"""
    analyzer = ChanAnalyzer()
    result = analyzer.analyze("TEST", _zigzag_bars())

    assert len(result.strokes) >= 3, "构造数据应至少形成3笔"
    assert result.strokes[-1].confirmed is False
    assert all(s.confirmed for s in result.strokes[:-1])


def test_segment_confirmed_once_left():
    """线段仅在仍含最后一笔（右侧前沿）时未确认；被后续笔离开后应确认。"""
    analyzer = ChanAnalyzer()
    result = analyzer.analyze("TEST", _zigzag_bars())

    last_stroke = result.strokes[-1] if result.strokes else None
    for seg in result.segments:
        still_frontier = bool(seg.strokes) and seg.strokes[-1] is last_stroke
        assert seg.confirmed == (not still_frontier)


def test_pivot_confirmed_once_left():
    """中枢仅在仍含最末元素（还在延伸）时未确认；被后续走势离开后应确认。"""
    analyzer = ChanAnalyzer()
    result = analyzer.analyze("TEST", _zigzag_bars())

    last_stroke = result.strokes[-1] if result.strokes else None
    for p in result.stroke_pivots:
        still_extending = bool(p.elements) and p.elements[-1] is last_stroke
        assert p.confirmed == (not still_extending)


def test_pending_notes_populated():
    """存在未确认结构时，pending_notes 与 has_pending_structure 应反映出来。"""
    analyzer = ChanAnalyzer()
    result = analyzer.analyze("TEST", _zigzag_bars())

    assert result.has_pending_structure is True
    assert result.pending_notes
    # 未确认结构应体现在最右侧提示里（至少提到“笔”）
    assert any("笔" in note for note in result.pending_notes)


def test_pending_notes_in_recommendation_caveats():
    """pending_notes 应被并入操作建议的风险提示中。"""
    analyzer = ChanAnalyzer()
    result = analyzer.analyze("TEST", _zigzag_bars())

    assert result.recommendation is not None
    for note in result.pending_notes:
        assert note in result.recommendation.caveats


def test_signal_on_last_stroke_unconfirmed():
    """落在未确认笔上的信号应标注 confirmed=False。"""
    analyzer = ChanAnalyzer()
    result = analyzer.analyze("TEST", _zigzag_bars())

    unconfirmed_end_times = {s.end_time for s in result.strokes if not s.confirmed}
    for sig in result.signals:
        if sig.time in unconfirmed_end_times:
            assert sig.confirmed is False
        else:
            assert sig.confirmed is True
