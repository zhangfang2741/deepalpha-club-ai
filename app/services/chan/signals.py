"""缠论三类买卖点生成"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.chan.divergence import DivergenceResult
from app.services.chan.i18n import is_en
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
    # 信号是否已确认：落在未确认（最后一笔）之上的信号需后续K线验证
    confirmed: bool = True
    # 输出语言（由 generate_all_signals 统一注入），驱动 label 的中英
    lang: str = "zh"

    @property
    def label(self) -> str:
        if is_en(self.lang):
            labels_en = {
                "buy1": "1st Buy", "buy2": "2nd Buy", "buy3": "3rd Buy",
                "sell1": "1st Sell", "sell2": "2nd Sell", "sell3": "3rd Sell",
            }
            return labels_en.get(self.type, self.type)
        labels = {
            "buy1": "一买", "buy2": "二买", "buy3": "三买",
            "sell1": "一卖", "sell2": "二卖", "sell3": "三卖",
        }
        return labels.get(self.type, self.type)

    @property
    def is_buy(self) -> bool:
        return self.type.startswith("buy")


def generate_buy1_signals(
    strokes: list[Stroke],
    divergences: list[DivergenceResult],
    lang: str = "zh",
) -> list[Signal]:
    """一类买点：下降笔末端出现底背驰。
    价格创新低，但MACD动量衰减（面积背驰），形成最强买点。
    """
    signals: list[Signal] = []
    for stroke, div in zip(strokes, divergences, strict=False):
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
                f"Type-1 buy: down-leg formed a "
                f"{'trend' if div.type == 'trend' else 'consolidation'} bottom divergence at "
                f"{stroke.end_time}, MACD area ratio={div.area_ratio:.2f}. {div.description}"
                if is_en(lang) else
                f"一类买点：下降笔在 {stroke.end_time} 出现{div.type == 'trend' and '趋势' or '盘整'}底背驰，"
                f"MACD面积比值={div.area_ratio:.2f}，{div.description}"
            ),
        ))
    return signals


def generate_sell1_signals(
    strokes: list[Stroke],
    divergences: list[DivergenceResult],
    lang: str = "zh",
) -> list[Signal]:
    """一类卖点：上升笔末端出现顶背驰。
    """
    signals: list[Signal] = []
    for stroke, div in zip(strokes, divergences, strict=False):
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
                f"Type-1 sell: up-leg formed a "
                f"{'trend' if div.type == 'trend' else 'consolidation'} top divergence at "
                f"{stroke.end_time}, MACD area ratio={div.area_ratio:.2f}. {div.description}"
                if is_en(lang) else
                f"一类卖点：上升笔在 {stroke.end_time} 出现{div.type == 'trend' and '趋势' or '盘整'}顶背驰，"
                f"MACD面积比值={div.area_ratio:.2f}，{div.description}"
            ),
        ))
    return signals


def generate_buy2_signals(
    strokes: list[Stroke],
    pivots: list[Pivot],
    lang: str = "zh",
) -> list[Signal]:
    """二类买点：中枢向上突破后，回踩进入中枢区间但不破下沿ZD。

    遍历中枢之后的每一对（向上突破笔 + 回调笔），回调落点在 [ZD, ZG] 内即为二买。
    """
    signals: list[Signal] = []
    for pivot in pivots:
        post = [s for s in strokes if s.start_time >= pivot.end_time]
        for i in range(len(post) - 1):
            breakout, retrace = post[i], post[i + 1]
            # 突破笔必须真正“跨越”中枢上沿（起点≤ZG<终点），
            # 排除价格已远离中枢后的笔被误判为突破
            if breakout.direction != "up" or not (
                breakout.start_price <= pivot.zg < breakout.end_price
            ):
                continue
            if retrace.direction != "down":
                continue
            # 回踩落在中枢区间内、未破下沿 ZD → 二买
            if pivot.zd <= retrace.end_price <= pivot.zg:
                signals.append(Signal(
                    type="buy2",
                    time=retrace.end_time,
                    price=retrace.end_price,
                    strength="medium",
                    divergence=None,
                    description=(
                        f"Type-2 buy: at {retrace.end_time}, after breaking above the pivot "
                        f"({pivot.zd:.2f}-{pivot.zg:.2f}), price pulled back to {retrace.end_price:.2f}, "
                        f"staying inside the pivot without breaking ZD ({pivot.zd:.2f}) — confirms a type-2 buy"
                        if is_en(lang) else
                        f"二类买点：{retrace.end_time} 中枢({pivot.zd:.2f}-{pivot.zg:.2f})向上突破后"
                        f"回踩至{retrace.end_price:.2f}，落在中枢内未破ZD({pivot.zd:.2f})，确认二买"
                    ),
                ))
    return signals


def generate_sell2_signals(
    strokes: list[Stroke],
    pivots: list[Pivot],
    lang: str = "zh",
) -> list[Signal]:
    """二类卖点：中枢向下跌破后，反抽进入中枢区间但不过上沿ZG。"""
    signals: list[Signal] = []
    for pivot in pivots:
        post = [s for s in strokes if s.start_time >= pivot.end_time]
        for i in range(len(post) - 1):
            breakout, retrace = post[i], post[i + 1]
            # 突破笔必须真正“跨越”中枢下沿（起点≥ZD>终点），
            # 排除价格已远离中枢后的笔被误判为跌破
            if breakout.direction != "down" or not (
                breakout.start_price >= pivot.zd > breakout.end_price
            ):
                continue
            if retrace.direction != "up":
                continue
            # 反抽落在中枢区间内、未过上沿 ZG → 二卖
            if pivot.zd <= retrace.end_price <= pivot.zg:
                signals.append(Signal(
                    type="sell2",
                    time=retrace.end_time,
                    price=retrace.end_price,
                    strength="medium",
                    divergence=None,
                    description=(
                        f"Type-2 sell: at {retrace.end_time}, after breaking below the pivot "
                        f"({pivot.zd:.2f}-{pivot.zg:.2f}), price bounced to {retrace.end_price:.2f}, "
                        f"staying inside the pivot without exceeding ZG ({pivot.zg:.2f}) — confirms a type-2 sell"
                        if is_en(lang) else
                        f"二类卖点：{retrace.end_time} 中枢({pivot.zd:.2f}-{pivot.zg:.2f})向下跌破后"
                        f"反抽至{retrace.end_price:.2f}，落在中枢内未过ZG({pivot.zg:.2f})，确认二卖"
                    ),
                ))
    return signals


def generate_buy3_signals(
    strokes: list[Stroke],
    pivots: list[Pivot],
    lang: str = "zh",
) -> list[Signal]:
    """三类买点：中枢向上突破后，回踩不回中枢（回调低点高于上沿ZG）。

    与二买的区别在回踩落点：高于 ZG 不回中枢即为三买（趋势确认，更强）。
    """
    signals: list[Signal] = []
    for pivot in pivots:
        post = [s for s in strokes if s.start_time >= pivot.end_time]
        for i in range(len(post) - 1):
            breakout, retrace = post[i], post[i + 1]
            # 突破笔必须真正“跨越”中枢上沿（起点≤ZG<终点），
            # 排除价格已远离中枢后的笔被误判为突破
            if breakout.direction != "up" or not (
                breakout.start_price <= pivot.zg < breakout.end_price
            ):
                continue
            if retrace.direction != "down":
                continue
            # 回踩低点高于上沿 ZG、未回中枢 → 三买
            if retrace.end_price > pivot.zg:
                signals.append(Signal(
                    type="buy3",
                    time=retrace.end_time,
                    price=retrace.end_price,
                    strength="strong",
                    divergence=None,
                    description=(
                        f"Type-3 buy: at {retrace.end_time}, after breaking above the pivot "
                        f"({pivot.zd:.2f}-{pivot.zg:.2f}), price pulled back to {retrace.end_price:.2f}, "
                        f"holding above ZG ({pivot.zg:.2f}) without re-entering — confirms a type-3 buy"
                        if is_en(lang) else
                        f"三类买点：{retrace.end_time} 突破中枢({pivot.zd:.2f}-{pivot.zg:.2f})后"
                        f"回踩至{retrace.end_price:.2f}，高于ZG({pivot.zg:.2f})未回中枢，确认三买"
                    ),
                ))
    return signals


def generate_sell3_signals(
    strokes: list[Stroke],
    pivots: list[Pivot],
    lang: str = "zh",
) -> list[Signal]:
    """三类卖点：中枢向下跌破后，反抽不回中枢（反弹高点低于下沿ZD）。"""
    signals: list[Signal] = []
    for pivot in pivots:
        post = [s for s in strokes if s.start_time >= pivot.end_time]
        for i in range(len(post) - 1):
            breakout, retrace = post[i], post[i + 1]
            # 突破笔必须真正“跨越”中枢下沿（起点≥ZD>终点），
            # 排除价格已远离中枢后的笔被误判为跌破
            if breakout.direction != "down" or not (
                breakout.start_price >= pivot.zd > breakout.end_price
            ):
                continue
            if retrace.direction != "up":
                continue
            # 反抽高点低于下沿 ZD、未回中枢 → 三卖
            if retrace.end_price < pivot.zd:
                signals.append(Signal(
                    type="sell3",
                    time=retrace.end_time,
                    price=retrace.end_price,
                    strength="strong",
                    divergence=None,
                    description=(
                        f"Type-3 sell: at {retrace.end_time}, after breaking below the pivot "
                        f"({pivot.zd:.2f}-{pivot.zg:.2f}), price bounced to {retrace.end_price:.2f}, "
                        f"staying below ZD ({pivot.zd:.2f}) without re-entering — confirms a type-3 sell"
                        if is_en(lang) else
                        f"三类卖点：{retrace.end_time} 跌破中枢({pivot.zd:.2f}-{pivot.zg:.2f})后"
                        f"反抽至{retrace.end_price:.2f}，低于ZD({pivot.zd:.2f})未回中枢，确认三卖"
                    ),
                ))
    return signals


def generate_all_signals(
    strokes: list[Stroke],
    divergences: list[DivergenceResult],
    pivots: list[Pivot],
    lang: str = "zh",
) -> list[Signal]:
    """生成所有买卖点信号，按时间排序"""
    signals: list[Signal] = []
    signals.extend(generate_buy1_signals(strokes, divergences, lang))
    signals.extend(generate_sell1_signals(strokes, divergences, lang))
    signals.extend(generate_buy2_signals(strokes, pivots, lang))
    signals.extend(generate_sell2_signals(strokes, pivots, lang))
    signals.extend(generate_buy3_signals(strokes, pivots, lang))
    signals.extend(generate_sell3_signals(strokes, pivots, lang))

    signals.sort(key=lambda s: s.time)

    # 去重：不同中枢（笔级/线段级、或延伸重叠）可能对同一笔对重复触发，
    # 同一时间 + 同一类型只保留一个
    seen: set[tuple[str, str]] = set()
    deduped: list[Signal] = []
    for s in signals:
        key = (s.type, s.time)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)
    for sig in deduped:
        sig.lang = lang
    return deduped
