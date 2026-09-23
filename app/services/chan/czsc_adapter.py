"""czsc 接入适配层：把项目内部 bars 格式转换为 czsc 原生对象。

只负责格式转换，不做任何缠论结构判断——结构判断交给 czsc 自身。
"""
from __future__ import annotations

import pandas as pd
from czsc import CZSC, Freq, RawBar


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
