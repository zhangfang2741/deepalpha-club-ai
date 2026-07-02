"""一目均衡表买卖信号识别：TK 交叉（转换线/基准线金叉死叉）与云突破。

信号强度由「信号发生时价格相对当前云的位置」决定，这是一目均衡表判读的核心：
同样是金叉，云上金叉（顺势）强、云中金叉（震荡）中、云下金叉（逆势）弱。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IchimokuSignal:
    """一目均衡表买卖信号。"""

    type: str        # tk_golden / tk_dead / kumo_up / kumo_down
    label: str       # 中文标签
    time: str
    price: float
    strength: str    # strong / medium / weak
    is_buy: bool
    description: str


def _cloud_at(
    span_a: list[float | None],
    span_b: list[float | None],
    bar_idx: int,
    displacement: int,
) -> tuple[float, float] | None:
    """返回在 bar_idx 处「当前显示」的云上下沿 (cloud_top, cloud_bottom)。

    因先行带前移 displacement 根，bar_idx 处显示的云由 bar_idx-displacement 处算得。
    数据不足则返回 None。
    """
    src = bar_idx - displacement
    if src < 0:
        return None
    a = span_a[src]
    b = span_b[src]
    if a is None or b is None:
        return None
    return (max(a, b), min(a, b))


def _price_position(close: float, cloud: tuple[float, float] | None) -> str:
    """价格相对云的位置：above（云上）/ below（云下）/ in（云中）/ na。"""
    if cloud is None:
        return "na"
    top, bottom = cloud
    if close > top:
        return "above"
    if close < bottom:
        return "below"
    return "in"


def generate_signals(
    bars: list[dict],
    conversion: list[float | None],
    base: list[float | None],
    span_a: list[float | None],
    span_b: list[float | None],
    displacement: int = 26,
) -> list[IchimokuSignal]:
    """扫描 K 线，生成 TK 交叉与云突破信号。"""
    signals: list[IchimokuSignal] = []

    for i in range(1, len(bars)):
        c_prev, c_cur = conversion[i - 1], conversion[i]
        b_prev, b_cur = base[i - 1], base[i]
        close = float(bars[i]["close"])
        time = str(bars[i]["time"])

        # ── TK 交叉（转换线 vs 基准线）──────────────────────────────
        if None not in (c_prev, c_cur, b_prev, b_cur):
            cloud = _cloud_at(span_a, span_b, i, displacement)
            pos = _price_position(close, cloud)

            golden = c_prev <= b_prev and c_cur > b_cur
            dead = c_prev >= b_prev and c_cur < b_cur

            if golden:
                strength = {"above": "strong", "in": "medium", "below": "weak"}.get(pos, "medium")
                signals.append(
                    IchimokuSignal(
                        type="tk_golden",
                        label="TK 金叉",
                        time=time,
                        price=close,
                        strength=strength,
                        is_buy=True,
                        description=(
                            f"转换线上穿基准线，形成金叉；价格位于{_pos_cn(pos)}，"
                            f"{_tk_cn(strength, buy=True)}"
                        ),
                    )
                )
            elif dead:
                strength = {"below": "strong", "in": "medium", "above": "weak"}.get(pos, "medium")
                signals.append(
                    IchimokuSignal(
                        type="tk_dead",
                        label="TK 死叉",
                        time=time,
                        price=close,
                        strength=strength,
                        is_buy=False,
                        description=(
                            f"转换线下穿基准线，形成死叉；价格位于{_pos_cn(pos)}，"
                            f"{_tk_cn(strength, buy=False)}"
                        ),
                    )
                )

        # ── 云突破（收盘价穿越云层）────────────────────────────────
        cloud_prev = _cloud_at(span_a, span_b, i - 1, displacement)
        cloud_cur = _cloud_at(span_a, span_b, i, displacement)
        if cloud_prev is not None and cloud_cur is not None:
            close_prev = float(bars[i - 1]["close"])
            top_prev, bot_prev = cloud_prev
            top_cur, bot_cur = cloud_cur

            # 前方云的颜色（当前 bar 处未来云的多空色）
            future_bull = _future_cloud_bullish(span_a, span_b, i, displacement)

            if close_prev <= top_prev and close > top_cur:
                signals.append(
                    IchimokuSignal(
                        type="kumo_up",
                        label="云上突破",
                        time=time,
                        price=close,
                        strength="strong" if future_bull else "medium",
                        is_buy=True,
                        description=(
                            "收盘价向上突破云层上沿，趋势转多"
                            + ("，且前方为阳云，动能更强" if future_bull else "，但前方为阴云，留意反复")
                        ),
                    )
                )
            elif close_prev >= bot_prev and close < bot_cur:
                signals.append(
                    IchimokuSignal(
                        type="kumo_down",
                        label="云下跌破",
                        time=time,
                        price=close,
                        strength="strong" if not future_bull else "medium",
                        is_buy=False,
                        description=(
                            "收盘价向下跌破云层下沿，趋势转空"
                            + ("，且前方为阴云，跌势更强" if not future_bull else "，但前方为阳云，留意反弹")
                        ),
                    )
                )

    return signals


def _future_cloud_bullish(
    span_a: list[float | None],
    span_b: list[float | None],
    bar_idx: int,
    displacement: int,
) -> bool:
    """当前 bar 处「向前平移后」的未来云是否为阳云（先行带 A 在 B 之上）。"""
    a = span_a[bar_idx]
    b = span_b[bar_idx]
    if a is None or b is None:
        return False
    return a >= b


def _pos_cn(pos: str) -> str:
    return {"above": "云层上方（顺势）", "below": "云层下方（逆势）", "in": "云层之中（震荡）"}.get(pos, "云层之外")


def _tk_cn(strength: str, *, buy: bool) -> str:
    if buy:
        return {"strong": "看涨信号较强", "medium": "看涨信号中等", "weak": "看涨信号偏弱"}.get(strength, "")
    return {"strong": "看跌信号较强", "medium": "看跌信号中等", "weak": "看跌信号偏弱"}.get(strength, "")
