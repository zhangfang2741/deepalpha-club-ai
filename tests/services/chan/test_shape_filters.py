"""形态过滤：czsc 形态信号 → 雷达剔除规则（纯函数部分）。"""

from typing import Any

import pytest

from app.services.chan.shape_filters import ShapeState, reject_reason


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
