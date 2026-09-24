"""买卖点信号引擎：用 czsc 的缠论结构信号逐根判定一/二/三类买卖点。

只负责「哪根K线、针对哪一笔、亮起了哪类买卖点」，不涉及强度与文案
（那些需要本地背驰度量与中枢，由 signals.generate_all_signals 组装）。

选型（均基于笔结构，不用纯 MACD 金叉死叉类信号）：
- 一买/一卖 cxt_first_buy/sell_V221126：最近 5~21 笔中末笔创新低/新高，
  价差力度弱于前段关键笔，且量能或笔长度也更弱（背驰）。
- 二买/二卖 cxt_second_bs_V240524：末笔终点分型与前 9 笔中 >=2 个长笔终点分型价格重叠。
- 三买/三卖 cxt_third_bs_V230318：前 5 笔构中枢，第 5 笔离开中枢不回，且三个转折点 SMA34 同向。

czsc 信号是持续多根K线的「状态」而非一次性事件，这里逐根推进（不回看未来），
在状态从「其他」切换为买卖点的那根K线记一次事件，并读取当时最后一笔已完成笔
作为信号所属笔；同一 (类型, 笔终点) 只保留首次。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from czsc import BarGenerator, CzscSignals, Freq

from app.services.chan.czsc_adapter import ts_date, bars_to_raw_bars

SignalType = Literal["buy1", "buy2", "buy3", "sell1", "sell2", "sell3"]

_V1_TO_TYPE: dict[str, SignalType] = {
    "一买": "buy1", "一卖": "sell1",
    "二买": "buy2", "二卖": "sell2",
    "三买": "buy3", "三卖": "sell3",
}

# 初始化 BarGenerator 的预热根数：单周期下只影响「从第几根开始逐根判定」，
# 不影响结构本身（CZSC 从第一根起就在算）；信号至少要若干笔才可能亮起。
_INIT_N = 20


@dataclass(frozen=True)
class BsEvent:
    """一次买卖点事件：bar_time 亮起，针对终点在 bi_end_time 的那一笔。"""
    type: SignalType
    bar_time: str
    bi_end_time: str
    bi_end_price: float
    span: str  # 一类信号命中的结构笔数（如 "9笔"），其余类型为空


def _signal_keys_and_config(label: str) -> tuple[list[str], list[dict]]:
    config = [
        {"name": "cxt_first_buy_V221126", "freq": label, "di": 1},
        {"name": "cxt_first_sell_V221126", "freq": label, "di": 1},
        {"name": "cxt_second_bs_V240524", "freq": label, "di": 1, "w": 9, "t": 2},
        {"name": "cxt_third_bs_V230318", "freq": label, "di": 1, "ma_type": "SMA", "timeperiod": 34},
    ]
    keys = [
        f"{label}_D1B_BUY1",
        f"{label}_D1B_SELL1",
        f"{label}_D1W9T2_第二买卖点V240524",
        f"{label}_D1#SMA#34_BS3辅助V230318",
    ]
    return keys, config


def scan_bs_events(bars: list[dict], *, symbol: str, freq: Freq) -> list[BsEvent]:
    """逐根推进 czsc 结构信号，返回按亮起时间排序、去重后的买卖点事件。"""
    raw = bars_to_raw_bars(bars, symbol=symbol, freq=freq)
    if len(raw) <= _INIT_N:
        return []

    label = freq.value
    keys, config = _signal_keys_and_config(label)
    bg = BarGenerator(label, [], max_count=len(raw) + 1)
    bg.init_freq_bars(label, raw[:_INIT_N])
    cs = CzscSignals(bg, config)

    prev = dict.fromkeys(keys, "其他")
    seen: set[tuple[str, str]] = set()
    events: list[BsEvent] = []
    for bar in raw[_INIT_N:]:
        cs.update_signals(bar)
        s = cs.s
        for key in keys:
            parts = s[key].split("_")
            v1 = parts[0]
            sig_type = _V1_TO_TYPE.get(v1)
            if sig_type is not None and prev[key] != v1:
                bi = cs.kas[label].bi_list[-1]
                bi_end_time = ts_date(bi.fx_b.dt)
                if (sig_type, bi_end_time) not in seen:
                    seen.add((sig_type, bi_end_time))
                    span = parts[1] if sig_type in ("buy1", "sell1") and parts[1].endswith("笔") else ""
                    events.append(BsEvent(
                        type=sig_type, bar_time=ts_date(bar.dt), bi_end_time=bi_end_time,
                        bi_end_price=float(bi.fx_b.fx), span=span,
                    ))
            prev[key] = v1
    return events
