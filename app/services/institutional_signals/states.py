"""状态引擎：把五维信号组合推导成状态标签（手册第二节的六大组合）。

产品只显示状态，不显示数据。每个状态附证据链，保证可解释、可回溯。
Phase 1 仅 Expectation + Participation 可用；依赖 Positioning/Fundamental/
Confirmation 的状态在数据接入后自动激活。
"""
from app.schemas.institutional_signals import DimensionScore, SignalState


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

    # 🔥 机构建仓：EPS/预期↑ + Call OI↑ + Call Vol↑ + IV↑（需 Positioning）
    if (exp and exp.score >= 55) and _hit(pos, "call_oi") and _hit(pos, "call_volume") and _hit(pos, "iv"):
        states.append(SignalState(
            key="institution_accumulation", emoji="🔥", label="机构建仓", stars=5,
            meaning="预期改善叠加期权真金下注，机构提前布局",
            evidence=["预期偏多", "Call OI 增加", "Call 放量", "IV 抬升"],
        ))

    # 💰 真资金进入：Call Vol↑ + OI↑ + IV↑ + 价格未动（需 Positioning）
    if _hit(pos, "call_volume") and _hit(pos, "call_oi") and _hit(pos, "iv") and not _hit(par, "breakout"):
        states.append(SignalState(
            key="smart_money", emoji="💰", label="真资金进入", stars=5,
            meaning="资金已到、价格未反应，最值得研究",
            evidence=["Call 放量", "OI 增加", "IV 抬升", "价格尚未突破"],
        ))

    # ⚡ 事件交易：IV↑ + Call Vol↑ + OI 基本不变（需 Positioning）
    iv = _sig(pos, "iv")
    oi = _sig(pos, "call_oi")
    if iv and iv.hit and _hit(pos, "call_volume") and oi and not oi.hit:
        states.append(SignalState(
            key="event_trading", emoji="⚡", label="事件交易", stars=4,
            meaning="IV 与 Call 齐涨但 OI 未增，多为短线投机而非真机构",
            evidence=["IV 暴涨", "Call 放量", "OI 基本不变"],
        ))

    # 🌱 基本面改善：Revenue↑ + Guidance↑ + Transcript 强调需求（需 Fundamental）
    if _hit(fun, "revenue_surprise") and _hit(fun, "guidance") and _hit(exp, "target_price"):
        states.append(SignalState(
            key="fundamental_turn", emoji="🌱", label="基本面改善", stars=5,
            meaning="营收与指引同步上修，企业经营真实转好",
            evidence=["营收超预期", "指引上调", "目标价上调"],
        ))

    # ❄ 资金撤退：EPS/预期↓ + Put OI↑ + Insider Sell + 放量
    if _hit_down(exp, "analyst_rating") and (_hit(pos, "put_oi") or _hit_down(con, "insider")):
        states.append(SignalState(
            key="distribution", emoji="❄", label="资金撤退", stars=4,
            meaning="预期下修叠加避险/减持，资金开始离开",
            evidence=["评级下调", "Put/减持信号"],
        ))

    if not states:
        states.append(SignalState(
            key="neutral", emoji="⚪", label="中性观望", stars=1,
            meaning="暂无显著机构资金组合信号",
            evidence=[],
        ))
    return states
