"""雷达形态过滤：czsc 形态信号 → 逐日形态状态 → 剔除规则。

只服务信号雷达的「假信号剔除」（设计见
docs/superpowers/specs/2026-09-27-radar-shape-filters-design.md），
不改变详情页买卖点口径。五条规则（按短路顺序）：

1. 假突破（bar_fake_break_V230204）：买点日=向上假突破（看空）剔、卖点日=向下
   假突破（看多）剔；反向假突破（跌破后收回）常正是一 / 二买自身形态，不剔。
2. 窄幅震荡（bar_zfzd_V241013 / V241014 任一满足）：横盘里没有可做的买卖点，剔。
3. 收盘位置（bar_classify_V240606 / V240607）：买点须收盘偏强（高位 或 看多，
   任一即可）、卖点须偏弱（低位 或 看空），否则剔。
4. 波动率分层（bar_volatility_V241013）：低波动组的信号质量差，剔；K 线不足
   w+n 根（三分位退化）时置「未知」跳过，不误杀。
5. 区间震荡（cxt_range_oscillation_V230620）：一类买卖点需要趋势前提，信号当天
   处于笔级区间震荡中的一类剔除；二 / 三类保留。

形态信号逐根推进、不回看未来，按「信号所属笔终点日」查表即为当时可知信息，
无未来函数。
"""

from __future__ import annotations

from dataclasses import dataclass

from czsc import CzscSignals

# czsc 形态信号参数（键名由这些参数渲染，改参数必须同步 read_shape_state 的键）。
_FAKE_BREAK_N = 20
_FAKE_BREAK_M = 5
_NARROW_N = 10
_VOLATILITY_W = 200
_VOLATILITY_N = 10
_RANGE_OSC_TH = 10  # czsc 默认 th=2（2% 中心振幅）对美股日线几乎不触发，取 10

_FIRST_BS = ("buy1", "sell1")


@dataclass(frozen=True)
class ShapeState:
    """某根K线（= 某个交易日）当时的形态状态。"""

    fake_break: str = "其他"  # 看多=向下假突破 / 看空=向上假突破 / 其他
    narrow_range: bool = False  # 窄幅震荡（V241013 / V241014 任一满足）
    close_pos: str = "中间"  # 高位 / 中间 / 低位
    k2_close_pos: str = "中性"  # 看多 / 看空 / 中性
    volatility: str = "未知"  # 低波动 / 中波动 / 高波动 / 未知（K 线不足）
    range_osc: str = "其他"  # X笔震荡 / 其他


def shape_config(label: str) -> list[dict]:
    """追加进 CzscSignals 的形态信号 config（与买卖点信号共用一次逐根推进）。"""
    return [
        {"name": "bar_fake_break_V230204", "freq": label, "di": 1, "n": _FAKE_BREAK_N, "m": _FAKE_BREAK_M},
        {"name": "bar_volatility_V241013", "freq": label, "w": _VOLATILITY_W, "n": _VOLATILITY_N},
        {"name": "bar_zfzd_V241013", "freq": label, "n": _NARROW_N},
        {"name": "bar_zfzd_V241014", "freq": label, "n": _NARROW_N},
        {"name": "bar_classify_V240606", "freq": label, "di": 1},
        {"name": "bar_classify_V240607", "freq": label, "di": 1},
        {"name": "cxt_range_oscillation_V230620", "freq": label, "di": 1, "th": _RANGE_OSC_TH},
    ]


def shape_keys(label: str) -> dict[str, str]:
    """read_shape_state 查询的 7 个 czsc 信号键（单一来源）。

    实现与键名对齐测试共用本函数：czsc 升级改键名时测试立刻红，避免
    read_shape_state 里 get() 缺键静默回退默认值导致规则整体失效。
    """
    return {
        # czsc 渲染该键不带版本后缀（实测），其余键带。
        "fake_break": f"{label}_D1N{_FAKE_BREAK_N}M{_FAKE_BREAK_M}_假突破",
        "volatility": f"{label}_波动率分层W{_VOLATILITY_W}N{_VOLATILITY_N}_完全分类V241013",
        "narrow_v241013": f"{label}_窄幅震荡N{_NARROW_N}_形态V241013",
        "narrow_v241014": f"{label}_窄幅震荡N{_NARROW_N}_形态V241014",
        "close_pos": f"{label}_D1收盘位置_分类V240606",
        "k2_close_pos": f"{label}_D1K2收盘位置_分类V240607",
        "range_osc": f"{label}_D1TH{_RANGE_OSC_TH}_区间震荡V230620",
    }


def read_shape_state(cs: CzscSignals, label: str, *, total_bars: int) -> ShapeState:
    """从逐根推进到当根的 CzscSignals 读出当日形态状态。

    total_bars 是本次推进的K线总数（不是已推进根数）：波动率分层需要 w+n 根
    缓存才有意义，不足时 czsc 会基于退化数据照常输出某档，必须显式置「未知」。
    """
    keys = shape_keys(label)

    def v1(key: str) -> str:
        return cs.s.get(key, "其他_任意_任意_0").split("_")[0]

    narrow = v1(keys["narrow_v241013"]) == "满足" or v1(keys["narrow_v241014"]) == "满足"
    volatility = "未知" if total_bars < _VOLATILITY_W + _VOLATILITY_N else v1(keys["volatility"])
    return ShapeState(
        fake_break=v1(keys["fake_break"]),
        narrow_range=narrow,
        close_pos=v1(keys["close_pos"]),
        k2_close_pos=v1(keys["k2_close_pos"]),
        volatility=volatility,
        range_osc=v1(keys["range_osc"]),
    )


def reject_reason(state: ShapeState | None, signal_type: str) -> str | None:
    """按五条规则判定一条买卖点是否该被雷达剔除，返回首个命中的过滤器名。

    signal_type 取值为 "buy1"~"sell3" 六值之一（见 czsc_signals.SignalType）。
    state 为 None（信号日早于逐根推进起点、查不到形态状态）时不剔除，防误杀。
    """
    if state is None:
        return None
    is_buy = signal_type.startswith("buy")
    if is_buy and state.fake_break == "看空":
        return "假突破"
    if not is_buy and state.fake_break == "看多":
        return "假突破"
    if state.narrow_range:
        return "窄幅震荡"
    if is_buy:
        if state.close_pos != "高位" and state.k2_close_pos != "看多":
            return "收盘位置"
    elif state.close_pos != "低位" and state.k2_close_pos != "看空":
        return "收盘位置"
    if state.volatility == "低波动":
        return "低波动"
    if signal_type in _FIRST_BS and state.range_osc != "其他":
        return "区间震荡"
    return None
