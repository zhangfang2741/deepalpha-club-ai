"""结构分层判断依据（structure_layers）测试。

延续 test_pivot_phase.py 的风格：手搭 Stroke/Segment/Signal 直接测
build_structure_layers，不跑完整分析流程。
"""
from __future__ import annotations

from typing import Literal

from app.services.chan.analyzer import ChanAnalysisResult
from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.segment import Segment
from app.services.chan.signals import Signal
from app.services.chan.stroke import Stroke
from app.services.chan.structure_layers import build_structure_layers


def _mc(idx: int, price: float) -> MergedCandle:
    return MergedCandle(idx=idx, time=f"D{idx:03d}", open=price, high=price + 1,
                         low=price - 1, close=price, raw_start=idx, raw_end=idx)


def _fx(kind: Literal["top", "bottom"], idx: int, price: float) -> Fractal:
    mid = _mc(idx, price)
    return Fractal(type=kind, candle=mid, left=_mc(idx - 1, price), right=_mc(idx + 1, price))


def _st(direction: Literal["up", "down"], idx: int, p0: float, p1: float,
        confirmed: bool = True) -> Stroke:
    sk: Literal["top", "bottom"] = "bottom" if direction == "up" else "top"
    ek: Literal["top", "bottom"] = "top" if direction == "up" else "bottom"
    return Stroke(direction=direction, start=_fx(sk, idx * 10, p0), end=_fx(ek, idx * 10 + 5, p1),
                  confirmed=confirmed)


def _seg(direction: Literal["up", "down"], strokes: list[Stroke], confirmed: bool = True) -> Segment:
    return Segment(direction=direction, strokes=strokes, confirmed=confirmed)


SignalType = Literal["buy1", "buy2", "buy3", "sell1", "sell2", "sell3"]


def _signal(kind: SignalType, confirmed: bool = True) -> Signal:
    return Signal(type=kind, time="D999", price=100.0, strength="strong",
                  divergence=None, description="", confirmed=confirmed)


def _result(strokes=None, segments=None, signals=None, pivot_phase=None) -> ChanAnalysisResult:
    r = ChanAnalysisResult(symbol="T", bars_count=0)
    r.strokes = strokes or []
    r.segments = segments or []
    r.signals = signals or []
    r.pivot_phase = pivot_phase
    return r


def test_empty_result_yields_no_layers():
    assert build_structure_layers(_result()) == []


def test_stroke_layer_unconfirmed_names_fractal_types():
    strokes = [_st("up", 0, 90, 98, confirmed=False)]
    layers = build_structure_layers(_result(strokes=strokes))
    assert len(layers) == 1
    layer = layers[0]
    assert layer.layer == "stroke"
    assert layer.label == "笔"
    assert "向上笔形成中" == layer.title
    assert "底" in layer.detail and "顶" in layer.detail and "尚未确认" in layer.detail


def test_stroke_layer_confirmed():
    strokes = [_st("down", 0, 100, 90, confirmed=True)]
    layers = build_structure_layers(_result(strokes=strokes))
    assert layers[0].title == "向下笔已确认"


def test_segment_layer_unconfirmed_and_confirmed():
    strokes = [_st("up", i, 90 + i, 98 + i) for i in range(3)]
    open_seg = _seg("up", strokes, confirmed=False)
    layers = build_structure_layers(_result(strokes=strokes, segments=[open_seg]))
    seg_layer = next(layer for layer in layers if layer.layer == "segment")
    assert seg_layer.title == "向上线段未结束"
    assert seg_layer.detail == "当前笔尚未破坏线段结构，线段延续。"

    closed_seg = _seg("down", strokes, confirmed=True)
    layers2 = build_structure_layers(_result(strokes=strokes, segments=[closed_seg]))
    seg_layer2 = next(layer for layer in layers2 if layer.layer == "segment")
    assert seg_layer2.title == "向下线段已确认"


def test_pivot_layer_reuses_pivot_phase_verbatim():
    from app.services.chan.pivot_phase import PivotPhase, StageGuide
    from app.services.chan.pivot import Pivot

    pivot = Pivot(zg=99, zd=91, gg=101, dd=89, start_time="T0", end_time="T1",
                  level="stroke", elements=[])
    phase = PivotPhase(phase="leaving", phase_label="向上离开中枢", direction="up", pivot=pivot,
                        checklist=[], reason="现价已站上ZG。", confirmed=True, branches=[],
                        stage_guide=StageGuide(current_index=2, steps=[], why_it_matters=""))
    layers = build_structure_layers(_result(pivot_phase=phase))
    pivot_layer = next(layer for layer in layers if layer.layer == "pivot")
    assert pivot_layer.title == "向上离开中枢"
    assert pivot_layer.detail == "现价已站上ZG。"


def test_signal_layer_candidate_vs_confirmed():
    unconfirmed = _signal("buy3", confirmed=False)
    layers = build_structure_layers(_result(signals=[unconfirmed]))
    sig_layer = next(layer for layer in layers if layer.layer == "signal")
    assert sig_layer.title == "三买候选"
    assert sig_layer.detail == "落在未确认笔上，属左侧预判。"

    confirmed = _signal("buy2", confirmed=True)
    layers2 = build_structure_layers(_result(signals=[confirmed]))
    sig_layer2 = next(layer for layer in layers2 if layer.layer == "signal")
    assert sig_layer2.title == confirmed.label
    assert "已被后续走势确认" in sig_layer2.detail


def test_layer_order_is_stroke_segment_pivot_signal():
    from app.services.chan.pivot_phase import PivotPhase, StageGuide
    from app.services.chan.pivot import Pivot

    strokes = [_st("up", i, 90 + i, 98 + i) for i in range(3)]
    seg = _seg("up", strokes, confirmed=False)
    pivot = Pivot(zg=99, zd=91, gg=101, dd=89, start_time="T0", end_time="T1",
                  level="stroke", elements=[])
    phase = PivotPhase(phase="leaving", phase_label="向上离开中枢", direction="up", pivot=pivot,
                        checklist=[], reason="", confirmed=True, branches=[],
                        stage_guide=StageGuide(current_index=2, steps=[], why_it_matters=""))
    signal = _signal("buy3", confirmed=False)
    layers = build_structure_layers(_result(strokes=strokes, segments=[seg], signals=[signal],
                                             pivot_phase=phase))
    assert [layer.layer for layer in layers] == ["stroke", "segment", "pivot", "signal"]
