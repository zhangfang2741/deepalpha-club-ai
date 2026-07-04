"""状态引擎：把五维信号组合推导成状态标签（手册第二节的六大组合）。

产品只显示状态，不显示数据。每个状态附证据链，保证可解释、可回溯。
Phase 1 仅 Expectation + Participation 可用；依赖 Positioning/Fundamental/
Confirmation 的状态在数据接入后自动激活。
"""
from app.schemas.institutional_signals import DimensionScore, SignalState
from app.services.institutional_signals.constants import STATE_BUY_META


def _sig(dim: DimensionScore | None, key: str):
    """从维度中取指定 signal，缺失返回 None。"""
    if dim is None:
        return None
    for s in dim.signals:
        if s.key == key:
            return s
    return None


def _hit(dim: DimensionScore | None, key: str) -> bool:
    s = _sig(dim, key)
    return bool(s and s.hit and s.direction == "up")


def _hit_down(dim: DimensionScore | None, key: str) -> bool:
    s = _sig(dim, key)
    return bool(s and s.hit and s.direction == "down")


def derive_states(dims: dict[str, DimensionScore]) -> list[SignalState]:
    """按重要度返回命中的状态；无组合命中时返回中性。"""
    exp = dims.get("expectation")
    pos = dims.get("positioning")
    par = dims.get("participation")
    fun = dims.get("fundamental")
    con = dims.get("confirmation")

    states: list[SignalState] = []

    # 📈 市场预期提升：TP↑ + Rating↑
    if _hit(exp, "target_price") and _hit(exp, "analyst_rating"):
        states.append(SignalState(
            key="expectation_upgrade", emoji="📈", label="市场预期提升", stars=5,
            meaning="卖方一致开始上修，往往形成中长期趋势",
            evidence=["目标价上调", "评级共识转多"],
        ))

    # 🚀 趋势确认：Relative Volume↑ + 价格突破 + 预期偏多
    if _hit(par, "relative_volume") and _hit(par, "breakout") and (exp and exp.score >= 55):
        states.append(SignalState(
            key="breakout_confirmation", emoji="🚀", label="趋势确认", stars=4,
            meaning="放量突破且预期向好，趋势得到确认",
            evidence=["放量", "收盘创 20 日新高", "预期维度偏多"],
        ))

    # Positioning 快照信号（key 对齐 compute_positioning）
    call_flow_up = _hit(pos, "call_flow")   # Put/Call 低 + Call 量/仓高 = 看涨下注
    iv_up = _hit(pos, "iv_level")           # ATM IV 偏高
    exp_strong = bool(exp and exp.score >= 55)
    relvol_up = _hit(par, "relative_volume")

    # 🔥 机构建仓：预期改善 + 期权看涨下注 + IV 抬升 + 现货放量
    accumulation = exp_strong and call_flow_up and iv_up and relvol_up
    if accumulation:
        states.append(SignalState(
            key="institution_accumulation", emoji="🔥", label="机构建仓", stars=5,
            meaning="预期改善叠加期权看涨下注与现货放量，机构提前布局",
            evidence=["预期偏多", "Call 资金流看涨", "IV 抬升", "现货放量"],
        ))

    # 💰 真资金进入：期权端看涨下注 + IV 抬升，但价格尚未突破
    if call_flow_up and iv_up and not _hit(par, "breakout"):
        states.append(SignalState(
            key="smart_money", emoji="💰", label="真资金进入", stars=5,
            meaning="期权端资金已下注、价格尚未反应，最值得研究",
            evidence=["Call 资金流看涨", "IV 抬升", "价格尚未突破"],
        ))

    # ⚡ 事件交易：IV + Call 齐动，但预期/现货未跟上，多为短线投机
    #   （手册原文用「OI 基本不变」区分真机构；快照无 OI 变化率，改用「预期未跟上」代理）
    if iv_up and call_flow_up and not exp_strong and not relvol_up and not accumulation:
        states.append(SignalState(
            key="event_trading", emoji="⚡", label="事件交易", stars=4,
            meaning="IV 与 Call 齐动但预期与现货未跟上，多为短线投机而非真机构",
            evidence=["IV 偏高", "Call 资金流活跃", "预期/现货未确认"],
        ))

    # 🌱 基本面改善：营收超预期 + 连续兑现 + 目标价上调
    #   （手册原文含 Guidance/Transcript；Guidance 需 NLP，暂用「连续兑现」替代）
    if _hit(fun, "revenue_surprise") and _hit(fun, "earnings_surprise") and _hit(exp, "target_price"):
        states.append(SignalState(
            key="fundamental_turn", emoji="🌱", label="基本面改善", stars=5,
            meaning="营收超预期叠加连续兑现与目标价上调，经营真实转好",
            evidence=["营收超预期", "连续 Beat", "目标价上调"],
        ))

    # ❄ 资金撤退：预期↓ + 看跌压力/减持
    if _hit_down(exp, "analyst_rating") and (_hit_down(pos, "put_pressure") or _hit_down(con, "insider")):
        states.append(SignalState(
            key="distribution", emoji="❄", label="资金撤退", stars=4,
            meaning="预期下修叠加看跌押注/减持，资金开始离开",
            evidence=["评级下调", "看跌压力/内部减持"],
        ))

    if not states:
        states.append(SignalState(
            key="neutral", emoji="⚪", label="中性观望", stars=1,
            meaning="暂无显著机构资金组合信号",
            evidence=[],
        ))

    # 附加买入视角元数据（仅偏多状态）
    for s in states:
        meta = STATE_BUY_META.get(s.key)
        if meta:
            s.buy_rank, s.buy_timing, s.buy_edge, s.buy_thesis = meta
    return states
