"""雷达形态过滤：czsc 形态信号 → 逐日形态状态 → 剔除规则。

只服务信号雷达的「假信号剔除」（设计见
docs/superpowers/specs/2026-09-27-radar-shape-filters-design.md），
不改变详情页买卖点口径。三条规则（按短路顺序）：

1. 假突破（bar_fake_break_V230204）：买点日=向上假突破（看空）剔、卖点日=向下
   假突破（看多）剔；反向假突破（跌破后收回）常正是一 / 二买自身形态，不剔。
2. 窄幅震荡（bar_zfzd_V241013 / V241014 任一满足）：横盘里没有可做的买卖点，剔。
3. 波动率分层（bar_volatility_V241013）：低波动组的信号质量差，剔；K 线不足
   w+n 根（三分位退化）时置「未知」跳过，不误杀。

判定日为信号成立日（雷达展示的日期），由调用方查表。收盘位置（bar_classify）与
区间震荡（cxt_range_oscillation）曾在设计内，真实成分股校准后移除：前者单根收盘
位置近似随机、在任何判定日都会无差别砍掉约 1/4 信号；后者砍掉一半一类信号且对
阈值不敏感，与一类自身的趋势前提重复。形态信号逐根推进、不回看未来。
"""

from __future__ import annotations

from dataclasses import dataclass

from czsc import CzscSignals

# czsc 形态信号参数（键名由这些参数渲染，改参数必须同步 shape_keys）。
_FAKE_BREAK_N = 20
_FAKE_BREAK_M = 5
_NARROW_N = 10
# 波动率分档值从第 ≈ w+130 根起产出（w=100~200 五点实测 220/240/250/270/320）；
# 分层还需序列本身有波动率对比，波动恒定的序列恒「其他」属正常退化（与 w 无关）。
# w=120 取值依据：产出更早且 500 根雷达窗口内有效覆盖更长。
# bars_seen（已见根数）不足 w+n=130 根时 read_shape_state 置「未知」跳过。
_VOLATILITY_W = 120
_VOLATILITY_N = 10


@dataclass(frozen=True)
class ShapeState:
    """某根K线（= 某个交易日）当时的形态状态。"""

    fake_break: str = "其他"  # 看多=向下假突破 / 看空=向上假突破 / 其他
    narrow_range: bool = False  # 窄幅震荡（V241013 / V241014 任一满足）
    volatility: str = "未知"  # 低波动 / 中波动 / 高波动 / 其他（czsc 尚未产出分档）/ 未知（K 线不足）


def shape_config(label: str) -> list[dict]:
    """追加进 CzscSignals 的形态信号 config（与买卖点信号共用一次逐根推进）。"""
    return [
        {"name": "bar_fake_break_V230204", "freq": label, "di": 1, "n": _FAKE_BREAK_N, "m": _FAKE_BREAK_M},
        {"name": "bar_volatility_V241013", "freq": label, "w": _VOLATILITY_W, "n": _VOLATILITY_N},
        {"name": "bar_zfzd_V241013", "freq": label, "n": _NARROW_N},
        {"name": "bar_zfzd_V241014", "freq": label, "n": _NARROW_N},
    ]


def shape_keys(label: str) -> dict[str, str]:
    """read_shape_state 查询的 czsc 信号键（单一来源）。

    实现与键名对齐测试共用本函数：czsc 升级改键名时测试立刻红，避免
    read_shape_state 里 get() 缺键静默回退默认值导致规则整体失效。
    """
    return {
        # czsc 渲染该键不带版本后缀（实测），其余键带。
        "fake_break": f"{label}_D1N{_FAKE_BREAK_N}M{_FAKE_BREAK_M}_假突破",
        "volatility": f"{label}_波动率分层W{_VOLATILITY_W}N{_VOLATILITY_N}_完全分类V241013",
        "narrow_v241013": f"{label}_窄幅震荡N{_NARROW_N}_形态V241013",
        "narrow_v241014": f"{label}_窄幅震荡N{_NARROW_N}_形态V241014",
    }


def read_shape_state(cs: CzscSignals, label: str, *, bars_seen: int) -> ShapeState:
    """从逐根推进到当根的 CzscSignals 读出当日形态状态。

    bars_seen 是截至当根已见的K线总根数（含预热段）：波动率分层需要 w+n 根
    缓存才有意义，不足时 czsc 会基于退化数据照常输出某档，必须显式置「未知」。
    """
    keys = shape_keys(label)

    def v1(key: str) -> str:
        return cs.s.get(key, "其他_任意_任意_0").split("_")[0]

    narrow = v1(keys["narrow_v241013"]) == "满足" or v1(keys["narrow_v241014"]) == "满足"
    volatility = "未知" if bars_seen < _VOLATILITY_W + _VOLATILITY_N else v1(keys["volatility"])
    return ShapeState(fake_break=v1(keys["fake_break"]), narrow_range=narrow, volatility=volatility)


def reject_reason(state: ShapeState | None, signal_type: str) -> str | None:
    """按三条规则判定一条买卖点是否该被雷达剔除，返回首个命中的过滤器名。

    signal_type 取值为 "buy1"~"sell3" 六值之一（见 czsc_signals.SignalType）。
    state 为 None（信号日早于逐根推进起点、查不到形态状态）时不剔除，防误杀。
    """
    if state is None:
        return None
    is_buy = signal_type.startswith("buy")
    if (is_buy and state.fake_break == "看空") or (not is_buy and state.fake_break == "看多"):
        return "假突破"
    if state.narrow_range:
        return "窄幅震荡"
    if state.volatility == "低波动":
        return "低波动"
    return None
