"""形态过滤：czsc 形态信号 → 雷达剔除规则（纯函数部分）。"""

import datetime as dt
import math
from typing import Any

import pytest
from czsc import BarGenerator, CzscSignals, Freq

from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.czsc_adapter import bars_to_raw_bars
from app.services.chan.czsc_signals import scan_bs_events
from app.services.chan.shape_filters import (
    ShapeState,
    read_shape_state,
    reject_reason,
    shape_config,
    shape_keys,
)
from tests.services.chan.test_signals import _decaying_downtrend_bars


def _state(**kwargs: Any) -> ShapeState:
    """构造一个「全部不触发剔除」的基准形态状态，测试里按需覆盖字段。"""
    base: dict[str, Any] = dict(fake_break="其他", narrow_range=False, volatility="中波动")
    base.update(kwargs)
    return ShapeState(**base)


ALL_TYPES = ("buy1", "buy2", "buy3", "sell1", "sell2", "sell3")


@pytest.mark.parametrize("signal_type", ALL_TYPES)
def test_clean_state_never_rejects(signal_type: str) -> None:
    assert reject_reason(_state(), signal_type) is None


def test_buy_rejected_on_upward_fake_break_only() -> None:
    """买点剔除向上假突破（看空）；向下假突破（看多）常是买点自身形态，不剔。"""
    assert reject_reason(_state(fake_break="看空"), "buy1") == "假突破"
    assert reject_reason(_state(fake_break="看多"), "buy1") is None


def test_sell_rejected_on_downward_fake_break_only() -> None:
    assert reject_reason(_state(fake_break="看多"), "sell1") == "假突破"
    assert reject_reason(_state(fake_break="看空"), "sell1") is None


@pytest.mark.parametrize("signal_type", ALL_TYPES)
def test_narrow_range_rejects_all_types(signal_type: str) -> None:
    assert reject_reason(_state(narrow_range=True), signal_type) == "窄幅震荡"


@pytest.mark.parametrize("signal_type", ALL_TYPES)
def test_low_volatility_rejects_all_types(signal_type: str) -> None:
    assert reject_reason(_state(volatility="低波动"), signal_type) == "低波动"


@pytest.mark.parametrize("volatility", ["未知", "其他", "中波动", "高波动"])
def test_non_low_volatility_never_rejects(volatility: str) -> None:
    """K 线不足（未知）、czsc 尚未产出分档（其他）、中 / 高波动都不剔。"""
    assert reject_reason(_state(volatility=volatility), "buy1") is None


def test_none_state_never_rejects() -> None:
    """形态状态缺失（如信号日早于预热段）不剔除，防误杀。"""
    assert reject_reason(None, "buy1") is None


def test_rules_short_circuit_in_documented_order() -> None:
    """多条件同时命中时返回首个（假突破 > 窄幅震荡 > 低波动）。"""
    assert reject_reason(_state(fake_break="看空", narrow_range=True, volatility="低波动"), "buy1") == "假突破"
    assert reject_reason(_state(narrow_range=True, volatility="低波动"), "buy1") == "窄幅震荡"


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
    """键名对齐：czsc 实际渲染的形态键必须与 read_shape_state 读取的键一致。

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
    state = read_shape_state(cs, label, bars_seen=len(raw))
    assert isinstance(state, ShapeState)
    # 全部键真实存在（缺失时 v1 会静默回退默认值，这里必须显式暴露）。
    # 键列表取自 shape_keys（与 read_shape_state 共用单一来源），改坏键名测试立刻红。
    for key in shape_keys(label).values():
        assert key in cs.s, key
    assert state.fake_break in {"看多", "看空", "其他"}


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
    """K 线不足 w+n（130）根：波动率一律「未知」，不信 czsc 的退化输出。"""
    bars = _trend_then_flat(n_flat=30)
    states: dict[str, ShapeState] = {}
    scan_bs_events(bars, symbol="TEST", freq=Freq.D, shape_states=states)
    assert all(s.volatility == "未知" for s in states.values())


def test_early_day_volatility_unknown_before_bars_seen_threshold() -> None:
    """序列足够长但信号日早于 w+n 根时，波动率按「已见根数」置「未知」。

    read_shape_state 的 bars_seen 传的是截至当根已见的K线总根数（含预热段）：
    230 根序列的第 101 根已见 101 根 < 130，波动率显式置「未知」，
    不依赖 czsc 对早期日期的退化输出（一旦退化输出变化行为也稳定）。
    """
    bars = _trend_then_flat(n_flat=30, n_extra=160)  # 40 + 30 + 160 = 230 根
    assert len(bars) >= 130
    states: dict[str, ShapeState] = {}
    scan_bs_events(bars, symbol="TEST", freq=Freq.D, shape_states=states)
    early_day = bars[100]["time"]  # 第 101 根：已见 101 根 < w+n=130
    assert states[early_day].volatility == "未知"
    # 阈值之后才读 czsc 分档值（第 131 根起已见 >= 130）
    late_day = bars[130]["time"]
    assert states[late_day].volatility != "未知"


def test_scan_bs_events_without_shape_states_unchanged() -> None:
    """不传 shape_states 时行为与现状完全一致（事件数不变）。"""
    bars = _trend_then_flat(n_flat=30)
    baseline = scan_bs_events(bars, symbol="TEST", freq=Freq.D)
    states: dict[str, ShapeState] = {}
    with_states = scan_bs_events(bars, symbol="TEST", freq=Freq.D, shape_states=states)
    assert [(e.type, e.bar_time) for e in with_states] == [(e.type, e.bar_time) for e in baseline]


def _sine_bars(segments: list[tuple[int, float]]) -> list[dict]:
    """分段 (根数, 振幅) 的确定性正弦序列：波动幅度可控且无随机性。"""
    seq: list[tuple[float, float, float, float]] = []
    p = 100.0
    i = 0
    for n, amp in segments:
        for _ in range(n):
            o = p
            c = p + math.sin(i / 4) * amp
            seq.append((o, max(o, c) + amp * 0.4, min(o, c) - amp * 0.4, c))
            p = c
            i += 1
    return _bars(seq)


def test_volatility_layering_actually_fires() -> None:
    """波动率分层真实触发守护：w 必须落在 czsc 实际可产出分档值的范围内。

    czsc 分档值从第 ≈ w+130 根起产出（w=100~200 五点实测），w=120 即约第 250 根起。
    序列取 130 根低波动 + 140 根剧烈波动（270 根 > 250，且两段波动差异明显），
    断言存在某天产出真实分档值；具体哪天、哪一档交给 czsc，避免对分档细节过拟合。
    """
    bars = _sine_bars([(130, 0.2), (140, 3.0)])
    states: dict[str, ShapeState] = {}
    scan_bs_events(bars, symbol="TEST", freq=Freq.D, shape_states=states)
    assert any(s.volatility in {"低波动", "中波动", "高波动"} for s in states.values())


# ---- analyzer 集成 ----


def test_analyze_shape_filters_switch() -> None:
    bars = _decaying_downtrend_bars()
    # 默认关闭：不算形态状态、买卖点与既有口径完全一致
    off = ChanAnalyzer().analyze("X", bars, mode="loose")
    assert off.shape_states == {}
    # 开启：有逐日形态状态，且不改变买卖点（详情页口径守护）
    on = ChanAnalyzer().analyze("X", bars, mode="loose", shape_filters=True)
    assert on.shape_states
    assert [(s.type, s.time) for s in on.signals] == [(s.type, s.time) for s in off.signals]
    # 形态状态键与信号日期同格式（纯日期），雷达可直接查表
    assert all(len(k) == 10 for k in on.shape_states)
