"""形态过滤：czsc 形态信号 → 雷达剔除规则（纯函数部分）。"""

import datetime as dt
from typing import Any

import pytest
from czsc import BarGenerator, CzscSignals, Freq

from app.services.chan.czsc_adapter import bars_to_raw_bars
from app.services.chan.czsc_signals import scan_bs_events
from app.services.chan.shape_filters import (
    ShapeState,
    read_shape_state,
    reject_reason,
    shape_config,
    shape_keys,
)


def _state(**kwargs: Any) -> ShapeState:
    """构造一个「全部不触发剔除」的基准形态状态，测试里按需覆盖字段。

    基准的收盘位置（高位 + 看多）只对买点安全：卖点用例须自行覆盖为
    偏弱（低位 / 看空任一），否则会先命中「收盘位置」规则。
    """
    base: dict[str, Any] = dict(
        fake_break="其他",
        narrow_range=False,
        close_pos="高位",
        k2_close_pos="看多",
        volatility="中波动",
        range_osc="其他",
    )
    base.update(kwargs)
    return ShapeState(**base)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"close_pos": "中间"},
        {"k2_close_pos": "中性"},
        {"close_pos": "低位", "k2_close_pos": "看多"},
        {"close_pos": "高位", "k2_close_pos": "看空"},
    ],
)
def test_buy_kept_when_either_close_signal_strong(kwargs: dict) -> None:
    """买点：收盘位置高位、K2 看多，任一满足即保留。"""
    assert reject_reason(_state(**kwargs), "buy1") is None


def test_buy_rejected_when_both_close_signals_weak() -> None:
    state = _state(close_pos="中间", k2_close_pos="中性")
    assert reject_reason(state, "buy3") == "收盘位置"


def test_sell_kept_when_either_close_signal_weak() -> None:
    assert reject_reason(_state(close_pos="低位"), "sell1") is None
    assert reject_reason(_state(k2_close_pos="看空"), "sell2") is None


def test_sell_rejected_when_both_close_signals_strong() -> None:
    state = _state(close_pos="高位", k2_close_pos="看多")
    assert reject_reason(state, "sell1") == "收盘位置"


def test_buy_rejected_on_upward_fake_break_only() -> None:
    """买点剔除向上假突破（看空）；向下假突破（看多）常是买点自身形态，不剔。"""
    assert reject_reason(_state(fake_break="看空"), "buy1") == "假突破"
    assert reject_reason(_state(fake_break="看多"), "buy1") is None


def test_sell_rejected_on_downward_fake_break_only() -> None:
    # 卖点须收盘偏弱（低位/看空任一），否则先命中「收盘位置」而非假突破规则。
    assert reject_reason(_state(fake_break="看多"), "sell1") == "假突破"
    assert reject_reason(_state(fake_break="看空", close_pos="低位"), "sell1") is None


def test_narrow_range_rejects_all_types() -> None:
    for t in ("buy1", "buy2", "buy3", "sell1", "sell2", "sell3"):
        assert reject_reason(_state(narrow_range=True), t) == "窄幅震荡"


def test_low_volatility_rejects_all_types() -> None:
    assert reject_reason(_state(volatility="低波动"), "buy1") == "低波动"
    assert reject_reason(_state(volatility="低波动", close_pos="低位"), "sell3") == "低波动"


def test_unknown_volatility_never_rejects() -> None:
    """K 线不足导致波动率未知时跳过该过滤，不误杀。"""
    assert reject_reason(_state(volatility="未知"), "buy1") is None
    assert reject_reason(_state(volatility="未知", close_pos="低位"), "sell1") is None


@pytest.mark.parametrize("signal_type", ["buy1", "sell1"])
def test_range_oscillation_rejects_first_bs_only(signal_type: str) -> None:
    """一类买卖点额外要求趋势环境：区间震荡中的一类剔除，二 / 三类保留。"""
    # 卖点须收盘偏弱（低位/看空任一），否则先命中「收盘位置」而非本条规则。
    sell_ok = {"close_pos": "低位"} if signal_type.startswith("sell") else {}
    assert reject_reason(_state(range_osc="3笔震荡", **sell_ok), signal_type) == "区间震荡"
    assert reject_reason(_state(range_osc="3笔震荡"), "buy2") is None
    assert reject_reason(_state(range_osc="3笔震荡", close_pos="低位"), "sell3") is None


def test_none_state_never_rejects() -> None:
    """形态状态缺失（如信号日早于预热段）不剔除，防误杀。"""
    assert reject_reason(None, "buy1") is None


def test_rules_short_circuit_in_documented_order() -> None:
    """多条件同时命中时返回首个（假突破 > 窄幅震荡 > 收盘位置 > 低波动 > 区间震荡）。"""
    state = _state(
        fake_break="看空",
        narrow_range=True,
        close_pos="中间",
        k2_close_pos="中性",
        volatility="低波动",
        range_osc="3笔震荡",
    )
    assert reject_reason(state, "buy1") == "假突破"
    assert reject_reason(_state(narrow_range=True, close_pos="中间"), "buy1") == "窄幅震荡"
    assert reject_reason(_state(close_pos="中间", k2_close_pos="中性", volatility="低波动"), "buy1") == "收盘位置"
    assert reject_reason(_state(volatility="低波动", range_osc="3笔震荡"), "buy1") == "低波动"


def _bars(seq: list[tuple[float, float, float, float]]) -> list[dict]:
    """把 (open, high, low, close) 元组序列转成 czsc_adapter 可消费的 bar dict。"""
    day0 = dt.date(2025, 1, 1)
    return [
        {
            "time": (day0 + dt.timedelta(days=i)).isoformat(),
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": 1000,
        }
        for i, (o, h, lo, c) in enumerate(seq)
    ]


def test_shape_signal_keys_align_with_czsc_runtime() -> None:
    """键名对齐：czsc 实际渲染的 7 个形态键必须与 read_shape_state 读取的键一致。

    czsc 模板字符串与 Rust 运行时渲染可能不一致（假突破键实测不带版本后缀），
    read_shape_state 里 get() 缺键会静默回退默认值导致规则整体失效，
    这里用真实 CzscSignals 驱动显式暴露键名漂移。
    """
    seq = []
    p = 100.0
    for _ in range(60):  # 60 根缓慢趋势，足够 CzscSignals 初始化产出全部键
        seq.append((p, p + 0.6, p - 0.2, p + 0.5))
        p += 0.5
    raw = bars_to_raw_bars(_bars(seq), symbol="TEST", freq=Freq.D)
    label = Freq.D.value
    bg = BarGenerator(label, [], max_count=len(raw) + 1)
    bg.init_freq_bars(label, raw[:20])
    cs = CzscSignals(bg, shape_config(label))
    for bar in raw[20:]:
        cs.update_signals(bar)
    state = read_shape_state(cs, label, total_bars=len(raw))
    assert isinstance(state, ShapeState)
    # 全部 7 个键真实存在（缺失时 v1 会静默回退默认值，这里必须显式暴露）。
    # 键列表取自 shape_keys（与 read_shape_state 共用单一来源），改坏键名测试立刻红。
    for key in shape_keys(label).values():
        assert key in cs.s, key
    # 收盘位置两条信号的运行时取值集合：缺键回退「其他」/「中性」会让收盘位置
    # 规则 fail-unsafe（买点恒剔、卖点恒留），把取值集合也钉在这里。
    assert state.close_pos in {"高位", "中间", "低位"}
    assert state.k2_close_pos in {"看多", "看空", "中性"}


# ---- 逐根推进集成：scan_bs_events 产出 shape_states ----


def _trend_then_flat(n_flat: int = 20, n_extra: int = 0) -> list[dict]:
    """40 根趋势 + n_flat 根窄幅横盘（可选 n_extra 根续涨）：横盘段应触发窄幅震荡。

    横盘需约 20 根才触发 bar_zfzd（n=10 但判定窗口含趋势尾巴，实测 14 根不触发）。
    """
    seq: list[tuple[float, float, float, float]] = []
    p = 100.0
    for _ in range(40):
        seq.append((p, p + 0.6, p - 0.2, p + 0.5))
        p += 0.5
    for _ in range(n_flat):
        seq.append((p, p + 0.05, p - 0.05, p + 0.01))
    for _ in range(n_extra):
        seq.append((p, p + 0.6, p - 0.2, p + 0.5))
        p += 0.5
    return _bars(seq)


def test_scan_bs_events_records_shape_states_per_day() -> None:
    """逐根推进从第 21 根开始，每个交易日都记录一条形态状态。"""
    bars = _trend_then_flat()
    states: dict[str, ShapeState] = {}
    scan_bs_events(bars, symbol="TEST", freq=Freq.D, shape_states=states)
    # 逐根推进从第 21 根开始，每天都有一条状态
    assert len(states) == len(bars) - 20
    # 窄幅横盘段（最后一根一定在横盘中）触发窄幅震荡
    last_day = bars[-1]["time"]
    assert states[last_day].narrow_range is True
    # 趋势段中段不触发
    mid_day = bars[30]["time"]
    assert states[mid_day].narrow_range is False


def test_shape_states_volatility_unknown_when_bars_insufficient() -> None:
    """K 线不足 w+n（210）根：波动率一律「未知」，不信 czsc 的退化输出。"""
    bars = _trend_then_flat(n_flat=30)
    states: dict[str, ShapeState] = {}
    scan_bs_events(bars, symbol="TEST", freq=Freq.D, shape_states=states)
    assert all(s.volatility == "未知" for s in states.values())


def test_early_day_volatility_never_low_when_total_bars_sufficient() -> None:
    """序列足够长（>=210 根，未知守护不生效）但信号日早于第 210 根时的退化守护。

    read_shape_state 的 total_bars 传的是本次推进的K线总数而非已推进根数，
    早期日期的波动率直接暴露 czsc 退化输出；实测为「其他」（fail-safe，
    不触发低波动剔除），一旦 czsc 升级改为输出「低波动」本测试立刻红。
    """
    bars = _trend_then_flat(n_flat=30, n_extra=160)  # 40 + 30 + 160 = 230 根
    assert len(bars) >= 210
    states: dict[str, ShapeState] = {}
    scan_bs_events(bars, symbol="TEST", freq=Freq.D, shape_states=states)
    early_day = bars[100]["time"]  # 前 200 根内、晚于逐根推进起点（第 21 根）
    assert states[early_day].volatility in {"其他", "未知", "中波动", "高波动"}


def test_scan_bs_events_without_shape_states_unchanged() -> None:
    """不传 shape_states 时行为与现状完全一致（事件数不变）。"""
    bars = _trend_then_flat(n_flat=30)
    baseline = scan_bs_events(bars, symbol="TEST", freq=Freq.D)
    states: dict[str, ShapeState] = {}
    with_states = scan_bs_events(bars, symbol="TEST", freq=Freq.D, shape_states=states)
    assert [(e.type, e.bar_time) for e in with_states] == [(e.type, e.bar_time) for e in baseline]
