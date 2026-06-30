"""缠论三类买卖点生成"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.chan.divergence import DivergenceResult
from app.services.chan.pivot import Pivot
from app.services.chan.stroke import Stroke


@dataclass
class Signal:
    """买卖点信号"""
    type: Literal["buy1", "buy2", "buy3", "sell1", "sell2", "sell3"]
    time: str
    price: float
    strength: Literal["strong", "medium", "weak"]
    divergence: DivergenceResult | None
    description: str

    @property
    def label(self) -> str:
        labels = {
            "buy1": "一买", "buy2": "二买", "buy3": "三买",
            "sell1": "一卖", "sell2": "二卖", "sell3": "三卖",
        }
        return labels.get(self.type, self.type)

    @property
    def is_buy(self) -> bool:
        return self.type.startswith("buy")


def _divergence_to_strength(div: DivergenceResult | None) -> Literal["strong", "medium", "weak"]:
    if div is None or not div.is_diverged:
        return "weak"
    return div.strength  # type: ignore[return-value]


def generate_buy1_signals(
    strokes: list[Stroke],
    divergences: list[DivergenceResult],
) -> list[Signal]:
    """一类买点：下降笔末端出现底背驰。
    价格创新低，但MACD动量衰减（面积背驰），形成最强买点。
    """
    signals: list[Signal] = []
    for i, (stroke, div) in enumerate(zip(strokes, divergences)):
        if stroke.direction != "down":
            continue
        if not div.is_diverged:
            continue

        strength = div.strength  # type: ignore[assignment]
        signals.append(Signal(
            type="buy1",
            time=stroke.end_time,
            price=stroke.end_price,
            strength=strength,
            divergence=div,
            description=(
                f"一类买点：下降笔在 {stroke.end_time} 出现{div.type == 'trend' and '趋势' or '盘整'}底背驰，"
                f"MACD面积比值={div.area_ratio:.2f}，{div.description}"
            ),
        ))
    return signals


def generate_sell1_signals(
    strokes: list[Stroke],
    divergences: list[DivergenceResult],
) -> list[Signal]:
    """一类卖点：上升笔末端出现顶背驰。
    """
    signals: list[Signal] = []
    for stroke, div in zip(strokes, divergences):
        if stroke.direction != "up":
            continue
        if not div.is_diverged:
            continue

        strength = div.strength  # type: ignore[assignment]
        signals.append(Signal(
            type="sell1",
            time=stroke.end_time,
            price=stroke.end_price,
            strength=strength,
            divergence=div,
            description=(
                f"一类卖点：上升笔在 {stroke.end_time} 出现{div.type == 'trend' and '趋势' or '盘整'}顶背驰，"
                f"MACD面积比值={div.area_ratio:.2f}，{div.description}"
            ),
        ))
    return signals


def generate_buy2_signals(
    strokes: list[Stroke],
    pivots: list[Pivot],
) -> list[Signal]:
    """二类买点：中枢形成后，价格突破中枢上沿(ZG)，回踩不破ZD即为二买。
    特征：在中枢之后，第一次回调不破中枢ZD。
    """
    signals: list[Signal] = []
    if not pivots:
        return signals

    for pivot in pivots:
        # 找中枢结束后的笔序列
        pivot_end_t = pivot.end_time
        post_strokes = [s for s in strokes if s.start_time >= pivot_end_t]
        if len(post_strokes) < 2:
            continue

        # 突破笔（向上离开中枢）
        breakout = post_strokes[0]
        if breakout.direction != "up" or breakout.end_price <= pivot.zg:
            continue

        # 回调笔
        retrace = post_strokes[1]
        if retrace.direction != "down":
            continue

        # 回调最低点不破中枢ZD → 二买
        if retrace.end_price >= pivot.zd:
            signals.append(Signal(
                type="buy2",
                time=retrace.end_time,
                price=retrace.end_price,
                strength="medium",
                divergence=None,
                description=(
                    f"二类买点：{retrace.end_time} 中枢({pivot.zd:.2f}-{pivot.zg:.2f})突破后"
                    f"回踩至{retrace.end_price:.2f}，未破ZD({pivot.zd:.2f})，确认二买"
                ),
            ))

    return signals


def generate_sell2_signals(
    strokes: list[Stroke],
    pivots: list[Pivot],
) -> list[Signal]:
    """二类卖点：中枢形成后，价格跌破中枢下沿(ZD)，反弹不过ZG即为二卖。
    """
    signals: list[Signal] = []
    if not pivots:
        return signals

    for pivot in pivots:
        pivot_end_t = pivot.end_time
        post_strokes = [s for s in strokes if s.start_time >= pivot_end_t]
        if len(post_strokes) < 2:
            continue

        breakout = post_strokes[0]
        if breakout.direction != "down" or breakout.end_price >= pivot.zd:
            continue

        retrace = post_strokes[1]
        if retrace.direction != "up":
            continue

        if retrace.end_price <= pivot.zg:
            signals.append(Signal(
                type="sell2",
                time=retrace.end_time,
                price=retrace.end_price,
                strength="medium",
                divergence=None,
                description=(
                    f"二类卖点：{retrace.end_time} 中枢({pivot.zd:.2f}-{pivot.zg:.2f})跌破后"
                    f"反弹至{retrace.end_price:.2f}，未过ZG({pivot.zg:.2f})，确认二卖"
                ),
            ))

    return signals


def generate_buy3_signals(
    strokes: list[Stroke],
    pivots: list[Pivot],
) -> list[Signal]:
    """三类买点：线段离开中枢后，产生的第一个回调（低点高于中枢ZG）即为三买。
    条件更强，需要价格已完全脱离中枢范围。
    """
    signals: list[Signal] = []
    if not pivots:
        return signals

    for pivot in pivots:
        pivot_end_t = pivot.end_time
        post_strokes = [s for s in strokes if s.start_time >= pivot_end_t]
        if len(post_strokes) < 2:
            continue

        breakout = post_strokes[0]
        # 完全离开中枢（整个笔都在ZG以上）
        if breakout.direction != "up" or breakout.low <= pivot.zg:
            continue

        retrace = post_strokes[1]
        if retrace.direction != "down":
            continue

        # 回调最低点高于中枢ZG → 三买（最强）
        if retrace.end_price > pivot.zg:
            signals.append(Signal(
                type="buy3",
                time=retrace.end_time,
                price=retrace.end_price,
                strength="strong",
                divergence=None,
                description=(
                    f"三类买点：{retrace.end_time} 价格完全脱离中枢({pivot.zd:.2f}-{pivot.zg:.2f})，"
                    f"回调低点{retrace.end_price:.2f}高于ZG({pivot.zg:.2f})，确认三买"
                ),
            ))

    return signals


def generate_sell3_signals(
    strokes: list[Stroke],
    pivots: list[Pivot],
) -> list[Signal]:
    """三类卖点：价格完全脱离中枢下方，反弹高点低于中枢ZD → 三卖。
    """
    signals: list[Signal] = []
    if not pivots:
        return signals

    for pivot in pivots:
        pivot_end_t = pivot.end_time
        post_strokes = [s for s in strokes if s.start_time >= pivot_end_t]
        if len(post_strokes) < 2:
            continue

        breakout = post_strokes[0]
        if breakout.direction != "down" or breakout.high >= pivot.zd:
            continue

        retrace = post_strokes[1]
        if retrace.direction != "up":
            continue

        if retrace.end_price < pivot.zd:
            signals.append(Signal(
                type="sell3",
                time=retrace.end_time,
                price=retrace.end_price,
                strength="strong",
                divergence=None,
                description=(
                    f"三类卖点：{retrace.end_time} 价格完全脱离中枢({pivot.zd:.2f}-{pivot.zg:.2f})，"
                    f"反弹高点{retrace.end_price:.2f}低于ZD({pivot.zd:.2f})，确认三卖"
                ),
            ))

    return signals


def generate_all_signals(
    strokes: list[Stroke],
    divergences: list[DivergenceResult],
    pivots: list[Pivot],
) -> list[Signal]:
    """生成所有买卖点信号，按时间排序"""
    signals: list[Signal] = []
    signals.extend(generate_buy1_signals(strokes, divergences))
    signals.extend(generate_sell1_signals(strokes, divergences))
    signals.extend(generate_buy2_signals(strokes, pivots))
    signals.extend(generate_sell2_signals(strokes, pivots))
    signals.extend(generate_buy3_signals(strokes, pivots))
    signals.extend(generate_sell3_signals(strokes, pivots))

    signals.sort(key=lambda s: s.time)
    return signals
