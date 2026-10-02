"""买卖点信号引擎：用 czsc 逐根推进，给出买卖点事件、每一笔完成的时刻与（可选）逐日形态状态。

只负责「哪根K线、针对哪一笔、亮起了哪类信号」与「每一笔在哪根K线完成」，不涉及强度、
文案与前提检查——由各口径的组装函数负责（signal_policy：宽松 generate_loose_signals /
严格 generate_all_signals）。

按口径（signal_policy.czsc_families）启用哪些 czsc 信号族：
- first：一买/一卖 cxt_first_buy/sell_V221126（所有口径都用）——最近 5~21 笔中末笔创新低/
  新高，价差力度弱于前段关键笔，且量能或笔长度也更弱（力度背驰）。严格口径还要看趋势前提
  （signals._in_trend），只在盘整里的背驰不算；宽松口径盘整背驰也算。
- second / third：czsc 原生二 / 三类，**仅宽松（默认）口径**使用，由 loose2 的两条一致性约束
  兜底（同笔去重、无源二类丢弃，见 signals.generate_loose_signals）：
  - 二买/二卖 cxt_second_bs_V240524：末笔终点分型与前 9 笔中 >=2 个长笔终点分型价格重叠。
  - 三买/三卖 cxt_third_bs_V230318：前 5 笔构中枢，第 5 笔离开中枢不回，且三个转折点 SMA34 同向。
  严格口径不用它们（偏离缠论原文），改由 signals 按标准定义从笔与中枢推出，这里只提供
  每一笔完成的K线（stroke_done_at）作为检测时间，保证不回看未来。

czsc 信号是持续多根K线的「状态」而非一次性事件，这里逐根推进（不回看未来），
在状态从「其他」切换为买卖点的那根K线记一次事件，并读取当时最后一笔已完成笔
作为信号所属笔；同一 (类型, 笔终点) 只保留首次。

shape_states（雷达形态过滤，当前暂停应用）：传入时同一次推进顺带记录逐日形态状态。
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from czsc import BarGenerator, CzscSignals, Freq

from app.services.chan.czsc_adapter import ts_date, bars_to_raw_bars
from app.services.chan.leg_metric import LegForce
from app.services.chan.shape_filters import ShapeState, read_shape_state, shape_config

SignalType = Literal["buy1", "buy2", "buy3", "sell1", "sell2", "sell3"]
SignalFamily = Literal["first", "second", "third"]

_V1_TO_TYPE: dict[str, SignalType] = {
    "一买": "buy1", "一卖": "sell1",
    "二买": "buy2", "二卖": "sell2",
    "三买": "buy3", "三卖": "sell3",
}

# 初始化 BarGenerator 的预热根数：单周期下只影响「从第几根开始逐根判定」，
# 不影响结构本身（CZSC 从第一根起就在算）；信号至少要若干笔才可能亮起。
_INIT_N = 20


@dataclass(frozen=True)
class LegState:
    """Rust 信号 dp_trend_legs 在事件那根 K 线上的状态：趋势前提是否成立 + b / c 段原始力度。

    b / c 为 None 表示趋势成立但两段取不到（调用方保留 czsc 笔级判定）。
    """
    trend: bool
    b: LegForce | None = None
    c: LegForce | None = None


@dataclass(frozen=True)
class BsEvent:
    """一次买卖点事件：bar_time 亮起，针对终点在 bi_end_time 的那一笔。"""
    type: SignalType
    bar_time: str
    bi_end_time: str
    bi_end_price: float
    span: str  # 一类信号命中的结构笔数（如 "9笔"），其余类型为空
    legs: LegState | None = None  # 自有 Rust 信号给出的趋势 / b·c 段原始力度；标准 czsc 下为 None


_DP_BI_TRACK = "dp_bi_track_V261001"
_DP_TREND_LEGS = "dp_trend_legs_V261001"


def _dp_signals_available(name: str = _DP_BI_TRACK) -> bool:
    """自编译的 czsc（rust/czsc，带 dp_* 信号）才有；标准 PyPI 版没有，退回读 bi_list 副本。"""
    try:
        import czsc._native as native
        names = native.signals.list_signal_names()  # pyright: ignore[reportAttributeAccessIssue]
        return any(n.endswith(name) for n in names)
    except Exception:  # noqa: BLE001 — 探测失败一律当作不可用
        return False


_HAS_DP = _dp_signals_available()
_HAS_DP_LEGS = _dp_signals_available(_DP_TREND_LEGS)


def _dp_scan_available() -> bool:
    """自编译 czsc 带 dp_scan_bs（整段逐根扫描在 Rust 里完成）。"""
    try:
        import czsc._native as native
        return hasattr(native, "dp_scan_bs")
    except Exception:  # noqa: BLE001 — 探测失败一律当作不可用
        return False


_HAS_DP_SCAN = _dp_scan_available()


def _parse_leg(text: str) -> LegForce:
    price, volume, length, area = (float(x) for x in text.split("#"))
    return LegForce(price=price, volume=volume, length=int(length), area=area)


def parse_leg_state(value: str) -> LegState:
    """解析 dp_trend_legs 的信号值（如 `买趋势_28#600#12#3.4_15#350#9#1.1_0`）。"""
    parts = value.split("_")
    if parts[0] not in ("买趋势", "卖趋势"):
        return LegState(trend=False)
    if len(parts) < 3 or parts[1] == "无":
        return LegState(trend=True)
    return LegState(trend=True, b=_parse_leg(parts[1]), c=_parse_leg(parts[2]))


def _dp_ts(s: str) -> str:
    """Dp 信号里的 YYYYMMDDHHMM → 项目统一时间字符串（与 ts_date 同口径）。"""
    day = f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return day if s[8:12] == "0000" else f"{day} {s[8:10]}:{s[10:12]}"


def _family_specs(label: str) -> dict[str, tuple[list[str], list[dict]]]:
    """信号族 → (状态键, czsc 信号配置)。"""
    return {
        "first": (
            [f"{label}_D1B_BUY1", f"{label}_D1B_SELL1"],
            [{"name": "cxt_first_buy_V221126", "freq": label, "di": 1},
             {"name": "cxt_first_sell_V221126", "freq": label, "di": 1}],
        ),
        "second": (
            [f"{label}_D1W9T2_第二买卖点V240524"],
            [{"name": "cxt_second_bs_V240524", "freq": label, "di": 1, "w": 9, "t": 2}],
        ),
        "third": (
            [f"{label}_D1#SMA#34_BS3辅助V230318"],
            [{"name": "cxt_third_bs_V230318", "freq": label, "di": 1, "ma_type": "SMA", "timeperiod": 34}],
        ),
    }


def _signal_keys_and_config(
    label: str, families: Iterable[SignalFamily] = ("first",),
) -> tuple[list[str], list[dict]]:
    specs = _family_specs(label)
    keys: list[str] = []
    config: list[dict] = []
    for fam in ("first", "second", "third"):
        if fam in families:
            keys += specs[fam][0]
            config += specs[fam][1]
    return keys, config


def _scan_native(
    bars: list[dict], *, symbol: str, label: str, families: Iterable[SignalFamily], use_legs: bool,
    stroke_done_at: dict[str, str] | None, stroke_started_at: dict[str, str] | None,
) -> list[BsEvent] | None:
    """整段逐根扫描交给 Rust（dp_scan_bs，一次调用、期间释放 GIL）；任何异常返回 None，由调用方退回逐根循环。"""
    import czsc._native as native

    try:
        keys, config = _signal_keys_and_config(label, families)
        legs_key = f"{label}_D1趋势腿_DP辅助V261001" if use_legs else None
        if use_legs:
            config = [*config, {"name": _DP_TREND_LEGS, "freq": label, "di": 1}]
        events, done, started = native.dp_scan_bs(  # pyright: ignore[reportAttributeAccessIssue]
            symbol, label, [b["time"] for b in bars], [float(b["open"]) for b in bars],
            [float(b["high"]) for b in bars], [float(b["low"]) for b in bars], [float(b["close"]) for b in bars],
            [float(b["volume"]) for b in bars], config, keys,
            stroke_done_at is not None or stroke_started_at is not None, legs_key, _INIT_N,
        )
    except Exception:  # noqa: BLE001 — 原生路径任何失败都退回逐根循环，结果一致只是慢
        return None
    if stroke_done_at is not None:
        for k, v in done:
            stroke_done_at.setdefault(k, v)
    if stroke_started_at is not None:
        for k, v in started:
            stroke_started_at.setdefault(k, v)
    return [
        BsEvent(type=t, bar_time=bt, bi_end_time=et, bi_end_price=price, span=span,  # type: ignore[arg-type]
                legs=parse_leg_state(legs) if legs is not None else None)
        for t, bt, et, price, span, legs in events
    ]


def scan_bs_events(
    bars: list[dict], *, symbol: str, freq: Freq, stroke_done_at: dict[str, str] | None = None,
    stroke_started_at: dict[str, str] | None = None,
    families: Iterable[SignalFamily] = ("first",),
    shape_states: dict[str, ShapeState] | None = None,
) -> list[BsEvent]:
    """逐根推进 czsc 结构信号，返回按亮起时间排序、去重后的买卖点事件。

    families 决定启用哪些信号族，默认只有一类背驰。

    stroke_done_at：传入时逐根记录「笔终点 → 这一笔完成的那根K线」（czsc 的 bi_list
    只含已完成的笔，新出现的末笔即在当根完成），供二 / 三类作检测时间。

    stroke_started_at：传入时逐根记录「笔终点 → 从这里出发的下一笔第一次成笔的那根K线」。缠论里
    一笔由后一笔成笔来确认，严格口径用它作成立日（下一笔之后再延伸也不影响前一笔）。

    shape_states：传入时 config 追加形态过滤信号（shape_filters），逐根记录
    「日期 → 当日形态状态」，供雷达按信号日查表剔除假信号；None 时不算形态信号，
    行为与现状一致。与 stroke_done_at 同构，一次推进零重复计算。
    """
    label = freq.value
    # 严格口径（只启用一类）才需要趋势 / 两段力度；宽松口径不用
    use_legs = _HAS_DP_LEGS and "first" in families and "second" not in families and "third" not in families
    if _HAS_DP_SCAN and shape_states is None:
        native = _scan_native(bars, symbol=symbol, label=label, families=families, use_legs=use_legs,
                              stroke_done_at=stroke_done_at, stroke_started_at=stroke_started_at)
        if native is not None:
            return native

    raw = bars_to_raw_bars(bars, symbol=symbol, freq=freq)
    if len(raw) <= _INIT_N:
        return []

    keys, config = _signal_keys_and_config(label, families)
    use_dp = _HAS_DP and (stroke_done_at is not None or stroke_started_at is not None)
    if use_dp:
        config = [*config, {"name": _DP_BI_TRACK, "freq": label, "di": 1}]
    dp_key = f"{label}_D1笔轨迹_DP辅助V261001"
    legs_key = f"{label}_D1趋势腿_DP辅助V261001"
    if use_legs:
        config = [*config, {"name": _DP_TREND_LEGS, "freq": label, "di": 1}]
    if shape_states is not None:
        config = config + shape_config(label)
    bg = BarGenerator(label, [], max_count=len(raw) + 1)
    bg.init_freq_bars(label, raw[:_INIT_N])
    cs = CzscSignals(bg, config)

    prev = dict.fromkeys(keys, "其他")
    seen: set[tuple[str, str]] = set()
    events: list[BsEvent] = []
    # i 为截至当根已见的K线总根数（1-based，含前 _INIT_N 根预热）：波动率分层
    # 须知道「当时已见多少根」，序列总长不能代表信号日的信息量。
    # 性能：cs.kas[label] / .bi_list 每次都是整份结构的副本（耗时随K线数、笔数线性增长），
    # 逐根循环里重复取是 O(n²)。每根K线最多取一次 bi_list，并且只在真的需要时才取：
    # 要记笔完成 / 成笔时刻，或有信号亮起。
    track_bis = stroke_done_at is not None or stroke_started_at is not None
    for i, bar in enumerate(raw[_INIT_N:], start=_INIT_N + 1):
        cs.update_signals(bar)
        if shape_states is not None:
            shape_states[ts_date(bar.dt)] = read_shape_state(cs, label, bars_seen=i)
        bis: list | None = None

        def _bis() -> list:
            nonlocal bis
            if bis is None:
                bis = cs.kas[label].bi_list
            return bis

        s = cs.s
        if use_dp:
            # Rust 信号直接报告末笔的终点 / 起点，不必拷贝整份笔列表（O(1) 而不是 O(n)）
            parts = s[dp_key].split("_")
            if len(parts) >= 3 and parts[0] != "其他":
                day = ts_date(bar.dt)
                if stroke_done_at is not None:
                    stroke_done_at.setdefault(_dp_ts(parts[1]), day)
                if stroke_started_at is not None:
                    stroke_started_at.setdefault(_dp_ts(parts[2]), day)
        elif track_bis and _bis():
            if stroke_done_at is not None:
                stroke_done_at.setdefault(ts_date(_bis()[-1].fx_b.dt), ts_date(bar.dt))
            if stroke_started_at is not None:
                stroke_started_at.setdefault(ts_date(_bis()[-1].fx_a.dt), ts_date(bar.dt))
        for key in keys:
            parts = s[key].split("_")
            v1 = parts[0]
            sig_type = _V1_TO_TYPE.get(v1)
            if sig_type is not None and prev[key] != v1:
                bi = _bis()[-1]
                bi_end_time = ts_date(bi.fx_b.dt)
                if (sig_type, bi_end_time) not in seen:
                    seen.add((sig_type, bi_end_time))
                    span = parts[1] if sig_type in ("buy1", "sell1") and parts[1].endswith("笔") else ""
                    events.append(BsEvent(
                        type=sig_type, bar_time=ts_date(bar.dt), bi_end_time=bi_end_time,
                        bi_end_price=float(bi.fx_b.fx), span=span,
                        legs=parse_leg_state(s[legs_key]) if use_legs and sig_type in ("buy1", "sell1") else None,
                    ))
            prev[key] = v1
    return events
