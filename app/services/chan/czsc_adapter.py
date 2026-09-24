"""czsc 接入适配层：把项目内部 bars 格式转换为 czsc 原生对象。

只负责格式转换，不做任何缠论结构判断——结构判断交给 czsc 自身。
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from czsc import CZSC, Direction, Freq, Mark, RawBar

from app.services.chan.fractal import Fractal, MergedCandle
from app.services.chan.pivot import Pivot
from app.services.chan.stroke import Stroke


def bars_to_raw_bars(bars: list[dict], *, symbol: str, freq: Freq) -> list[RawBar]:
    """把项目内部 bars（time/open/high/low/close/volume）转成 czsc.RawBar 列表。

    bars 必须已按时间升序排列（analyzer.py 现有调用方保证了这一点）。
    czsc.RawBar 没有对应"成交额"的数据源，amount 用 close*volume 近似。
    """
    raw_bars: list[RawBar] = []
    for idx, bar in enumerate(bars):
        raw_bars.append(
            RawBar(
                symbol=symbol,
                dt=pd.Timestamp(bar["time"]),
                freq=freq,
                open=float(bar["open"]),
                close=float(bar["close"]),
                high=float(bar["high"]),
                low=float(bar["low"]),
                vol=float(bar["volume"]),
                amount=float(bar["close"]) * float(bar["volume"]),
                id=idx,
            )
        )
    return raw_bars


def build_czsc(bars: list[dict], *, symbol: str, freq: Freq, min_bi_len: int = 0) -> CZSC:
    """构造 czsc.CZSC 分析对象。

    一次性喂入完整 bars 序列（不走流式 update），这样才能复用现有的
    「warmup + visible_from 窗口锚定后裁剪」调用方式：调用方在可见窗口前
    多取一段 warmup K 线一起传进来，本函数不关心窗口裁剪，裁剪逻辑在
    上层 analyzer.py 里做（后续计划的范围）。
    """
    raw_bars = bars_to_raw_bars(bars, symbol=symbol, freq=freq)
    return CZSC(raw_bars, min_bi_len=min_bi_len)


@dataclass
class CzscStructures:
    """czsc 结构转换结果：形状与 ChanAnalysisResult 前几步产物一致。"""
    merged_candles: list[MergedCandle]
    fractals: list[Fractal]
    strokes: list[Stroke]
    stroke_pivots: list[Pivot]


def _ts_date(ts) -> str:
    # str(date()) 输出 YYYY-MM-DD；包一层 str 以兼容 pyright 对 NaTType 的联合类型标注
    return str(pd.Timestamp(ts).date())


def extract_structures(c: CZSC, bars: list[dict]) -> CzscStructures:
    """把 czsc 的分型/笔/笔级中枢转换回项目内部 dataclass。

    时间字符串一律从输入 bars 的 time 还原（通过 RawBar.id 映射），
    保证与 _clip_to_window 的字符串比较语义一致。

    去包含K线序列的重建：czsc 1.0.1 的 ``CZSC.bars_ubi`` 只保留未完成笔
    区域内的K线（笔确认后即被消费，实测 80 根输入只剩 9 根），不能直接
    当完整序列用。这里用「各笔 ``bi.bars`` ∪ ``bars_ubi``」按 dt 去重排序
    重建；首笔确认之前的前导K线会被 czsc 内部丢弃、不参与任何结构，
    因此 ``merged_candles`` 可能不从 raw_start=0 开始（属预期行为）。
    """
    time_by_id = {i: b["time"] for i, b in enumerate(bars)}

    # 重建完整去包含K线序列：NewBar 按 dt 去重（相邻笔共享端点分型K线）
    nb_by_dt: dict = {}
    for bi in c.bi_list:
        for nb in bi.bars:
            nb_by_dt[nb.dt] = nb
    for nb in c.bars_ubi:
        nb_by_dt[nb.dt] = nb
    seq = [nb_by_dt[k] for k in sorted(nb_by_dt)]
    pos_by_dt = {nb.dt: pos for pos, nb in enumerate(seq)}

    def nb_to_candle(nb) -> MergedCandle:
        raw = nb.elements
        return MergedCandle(
            idx=pos_by_dt[nb.dt],
            time=time_by_id[raw[-1].id],
            open=float(raw[0].open), close=float(raw[-1].close),
            high=float(nb.high), low=float(nb.low),
            raw_start=raw[0].id, raw_end=raw[-1].id,
        )

    merged = [nb_to_candle(nb) for nb in seq]

    def fx_to_fractal(fx) -> Fractal:
        left, mid, right = (nb_to_candle(nb) for nb in fx.elements)
        return Fractal(type="top" if fx.mark == Mark.G else "bottom",
                       candle=mid, left=left, right=right)

    fractals = [fx_to_fractal(fx) for fx in c.fx_list]

    def bi_to_stroke(bi) -> Stroke:
        direction = "up" if bi.direction == Direction.Up else "down"
        return Stroke(direction=direction, start=fx_to_fractal(bi.fx_a),
                      end=fx_to_fractal(bi.fx_b))

    strokes = [bi_to_stroke(bi) for bi in c.bi_list]
    stroke_by_start_time: dict[str, Stroke] = {}
    for s in strokes:
        stroke_by_start_time.setdefault(s.start_time, s)

    pivots = []
    for zs in c.zs_list:
        elements = [stroke_by_start_time[_ts_date(bi.fx_a.dt)] for bi in zs.bis]
        pivots.append(Pivot(
            zg=float(zs.zg), zd=float(zs.zd), gg=float(zs.gg), dd=float(zs.dd),
            start_time=_ts_date(zs.bis[0].fx_a.dt),
            end_time=_ts_date(zs.bis[-1].fx_b.dt),
            level="stroke", elements=elements,
        ))

    return CzscStructures(merged_candles=merged, fractals=fractals,
                          strokes=strokes, stroke_pivots=pivots)
