"""级别进度（笔级 / 线段级 走到哪一步）测试。

只读汇总层：验证时间周期标签映射、中枢计数、走势类型、阶段判定（延伸 / 离开 /
背驰叠加）随结构正确产出，且不依赖任何算法改动。
"""
from __future__ import annotations

from app.services.chan.analyzer import ChanAnalysisResult
from app.services.chan.divergence import DivergenceResult
from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.levels import build_level_progress
from app.services.chan.pivot import Pivot
from app.services.chan.stroke import Stroke


def _mc(idx: int, price: float) -> MergedCandle:
    return MergedCandle(idx=idx, time=f"D{idx:03d}", open=price, high=price + 1,
                        low=price - 1, close=price, raw_start=idx, raw_end=idx)


def _fx(kind: str, idx: int, price: float) -> Fractal:
    return Fractal(type=kind, candle=_mc(idx, price),
                   left=_mc(idx - 1, price), right=_mc(idx + 1, price))


def _stroke(direction: str, idx: int, p0: float, p1: float) -> Stroke:
    sk = "bottom" if direction == "up" else "top"
    ek = "top" if direction == "up" else "bottom"
    return Stroke(direction=direction, start=_fx(sk, idx * 10, p0), end=_fx(ek, idx * 10 + 5, p1))


def _div(is_div: bool) -> DivergenceResult:
    return DivergenceResult(is_diverged=is_div, type="trend" if is_div else "none",
                            strength="strong" if is_div else "none",
                            area_ratio=0.5 if is_div else 1.0, description="", dif_ratio=0.5)


def _pivot(zg: float, zd: float, confirmed: bool = True) -> Pivot:
    return Pivot(zg=zg, zd=zd, gg=zg + 5, dd=zd - 5, start_time="a", end_time="b",
                 level="stroke", elements=[], confirmed=confirmed)


def test_no_strokes_returns_empty():
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    assert build_level_progress(r) == []


def test_tf_label_maps_by_freq():
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    r.strokes = [_stroke("up", 0, 100, 110)]
    r.merged_candles = [_mc(0, 110)]
    daily = build_level_progress(r, freq="daily")
    assert daily[0].tf_label == "日线 1D"
    weekly = build_level_progress(r, freq="weekly")
    assert weekly[0].tf_label == "周线 1W"


def test_no_pivot_stage_reports_one_way_move():
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    r.strokes = [_stroke("up", 0, 100, 110)]
    r.merged_candles = [_mc(0, 110)]
    lp = build_level_progress(r)[0]
    assert lp.level == "stroke"
    assert lp.pivot_count == 0
    assert lp.walk_type == "none"
    assert "单边" in lp.stage_label
    assert "向上" in lp.stage_label


def test_extending_pivot_stage():
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    r.strokes = [_stroke("up", 0, 100, 110)]
    r.merged_candles = [_mc(0, 100)]  # 现价落在中枢内
    r.stroke_pivots = [_pivot(zg=105, zd=95, confirmed=False)]
    lp = build_level_progress(r)[0]
    assert lp.stage == "building"
    assert lp.pivot_count == 1
    assert "延伸中" in lp.stage_label


def test_leaving_up_with_top_divergence():
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    r.strokes = [_stroke("up", 0, 100, 110), _stroke("up", 1, 100, 130)]
    r.divergences = [_div(False), _div(True)]  # 最后的上升笔顶背驰
    r.merged_candles = [_mc(0, 120)]  # 现价站上 ZG(105)
    r.stroke_pivots = [_pivot(zg=105, zd=95, confirmed=True)]
    lp = build_level_progress(r)[0]
    assert lp.stage == "leaving_up"
    assert "顶背驰" in lp.stage_label


def test_leaving_down_stage():
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    r.strokes = [_stroke("down", 0, 110, 90)]
    r.merged_candles = [_mc(0, 80)]  # 现价跌破 ZD(95)
    r.stroke_pivots = [_pivot(zg=105, zd=95, confirmed=True)]
    lp = build_level_progress(r)[0]
    assert lp.stage == "leaving_down"


def test_uptrend_walk_type_from_two_ascending_pivots():
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    r.strokes = [_stroke("up", 0, 100, 110)]
    r.merged_candles = [_mc(0, 130)]
    r.stroke_pivots = [_pivot(zg=105, zd=95), _pivot(zg=125, zd=115)]
    lp = build_level_progress(r)[0]
    assert lp.walk_type == "up_trend"
    assert lp.pivot_count == 2


def test_segment_level_included_when_segments_exist():
    from app.services.chan.segment import Segment
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    r.strokes = [_stroke("up", 0, 100, 110)]
    r.merged_candles = [_mc(0, 110)]
    seg = Segment(direction="up",
                  strokes=[_stroke("up", 0, 100, 110), _stroke("down", 1, 110, 105),
                           _stroke("up", 2, 105, 120)])
    r.segments = [seg]
    levels = build_level_progress(r, freq="daily")
    assert [lp.level for lp in levels] == ["stroke", "segment"]
    assert levels[1].tf_label == "周线 1W"


def test_latest_signal_only_on_stroke_level():
    from app.services.chan.signals import Signal
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    r.strokes = [_stroke("up", 0, 100, 110)]
    r.merged_candles = [_mc(0, 110)]
    r.signals = [Signal(type="buy1", time="D010", price=100.0,
                        strength="strong", divergence=None, description="")]
    lp = build_level_progress(r)[0]
    assert lp.latest_signal_label is not None
    assert "一买" in lp.latest_signal_label


def test_intraday_tf_labels_5f_30f():
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    r.strokes = [_stroke("up", 0, 100, 110)]
    r.merged_candles = [_mc(0, 110)]
    from app.services.chan.segment import Segment
    r.segments = [Segment(direction="up", strokes=[_stroke("up", 0, 100, 110),
                  _stroke("down", 1, 110, 105), _stroke("up", 2, 105, 120)])]
    five = build_level_progress(r, freq="5min")
    assert five[0].tf_label == "5分 5F"      # 笔=本级别
    assert five[1].tf_label == "30分 30F"    # 线段=高一级别
    thirty = build_level_progress(r, freq="30min")
    assert thirty[0].tf_label == "30分 30F"
    assert thirty[1].tf_label == "日线 1D"


def test_english_detail():
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    r.strokes = [_stroke("up", 0, 100, 110)]
    r.merged_candles = [_mc(0, 110)]
    lp = build_level_progress(r, lang="en")[0]
    assert lp.level_name == "Stroke level"
    assert lp.tf_label == "Daily 1D"
