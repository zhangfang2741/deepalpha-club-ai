"""缠论背驰判断：力度口径（与 czsc 一类买卖点同一口径）。

背驰 = 价格创新高/新低，但价差力度弱于前一个同向段，且量能或时长至少一项也更弱
（对应 czsc check_first_buy/sell 的 bc_price && (bc_volume || bc_length)）。
力度三项取自 czsc 的笔（见 Stroke.power_price / power_volume / length），线段为所含笔汇总。

MACD 仍在此计算，仅用于 API 的 macd 字段（旧版 App 的副图），不参与任何判定。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.chan.i18n import is_en, pick
from app.services.chan.stroke import Stroke


@dataclass
class MACDData:
    """MACD指标数据"""
    times: list[str]
    dif: list[float]   # DIF线（MACD线）
    dea: list[float]   # DEA线（信号线）
    bar: list[float]   # MACD柱（DIF-DEA的2倍）


@dataclass
class DivergenceResult:
    """背驰判断结果（力度比 = 当前段 / 前一个同向段，<1 表示更弱）"""
    is_diverged: bool
    type: Literal["trend", "consolidation", "none"]  # 趋势背驰 / 盘整背驰 / 无背驰
    strength: Literal["strong", "medium", "weak", "none"]
    price_ratio: float  # 价差力度比（主判据，也决定强弱分档）
    description: str
    volume_ratio: float = 1.0  # 量能比
    length_ratio: float = 1.0  # 时长比（去包含K线根数）


def calc_ema(values: list[float], period: int) -> list[float]:
    """指数移动平均"""
    if not values:
        return []
    k = 2.0 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def calc_macd(bars: list[dict], fast: int = 12, slow: int = 26, signal: int = 9) -> MACDData:
    """计算MACD指标。

    使用标准EMA公式：DIF = EMA(close, fast) - EMA(close, slow)，
    DEA = EMA(DIF, signal)，MACD = 2*(DIF-DEA)。
    """
    if len(bars) < slow:
        times = [b["time"] for b in bars]
        n = len(bars)
        return MACDData(times=times, dif=[0.0] * n, dea=[0.0] * n, bar=[0.0] * n)

    closes = [b["close"] for b in bars]
    times = [b["time"] for b in bars]

    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)

    dif = [f - s for f, s in zip(ema_fast, ema_slow, strict=False)]
    dea = calc_ema(dif, signal)
    bar = [2 * (d - de) for d, de in zip(dif, dea, strict=False)]

    return MACDData(times=times, dif=dif, dea=dea, bar=bar)


def _ratio(cur: float, ref: float) -> float:
    """力度比；参照为 0 时视为「不弱」（1.0），不做除零。"""
    return round(cur / ref, 2) if ref > 0 else 1.0


def classify_strength(price_ratio: float) -> Literal["strong", "medium", "weak", "none"]:
    """按价差力度比分档：<0.6 强、<0.8 中、<1 弱，>=1 不构成背驰。

    阈值取自 30 只美股/港股/A 股约两年半的 169 个一类信号的价差比三分位点（0.60 / 0.79），
    三档大致各占三分之一。
    """
    if price_ratio >= 1.0:
        return "none"
    if price_ratio < 0.6:
        return "strong"
    if price_ratio < 0.8:
        return "medium"
    return "weak"


def force_text(price_ratio: float, volume_ratio: float, length_ratio: float, lang: str = "zh") -> str:
    """力度比的人话：价差/量能/时长各是参照的几成。"""
    return pick(
        lang,
        f"价差为前段的 {price_ratio:.2f} 倍、量能 {volume_ratio:.2f} 倍、时长 {length_ratio:.2f} 倍",
        f"price range {price_ratio:.2f}x, volume {volume_ratio:.2f}x, duration {length_ratio:.2f}x of the prior leg",
    )


def check_divergence(
    current: Stroke, compare: Stroke, in_consolidation: bool = False, lang: str = "zh",
) -> DivergenceResult:
    """比较当前段与前一个同向段的力度，判断是否背驰（调用方已确认价格创新高/新低）。

    current / compare 可为笔或线段（都有 power_price / power_volume / length / direction）。
    """
    price_ratio = _ratio(current.power_price, compare.power_price)
    volume_ratio = _ratio(current.power_volume, compare.power_volume)
    length_ratio = _ratio(float(current.length), float(compare.length))
    forces = force_text(price_ratio, volume_ratio, length_ratio, lang)

    weaker_price = price_ratio < 1.0
    weaker_aux = volume_ratio < 1.0 or length_ratio < 1.0
    if not (weaker_price and weaker_aux):
        if weaker_price:
            reason = pick(lang, f"价差虽缩小，但量能与时长都没有减弱（{forces}），力度未衰竭，不算背驰",
                          f"The price range shrank but neither volume nor duration weakened ({forces}); "
                          f"force isn't exhausted — not a divergence")
        else:
            reason = pick(lang, f"价差力度没有减弱（{forces}），未见背驰",
                          f"Price-range force didn't weaken ({forces}); no divergence")
        return DivergenceResult(is_diverged=False, type="none", strength="none", price_ratio=price_ratio,
                                description=reason, volume_ratio=volume_ratio, length_ratio=length_ratio)

    div_type: Literal["trend", "consolidation"] = "consolidation" if in_consolidation else "trend"
    strength = classify_strength(price_ratio)
    up = current.direction == "up"
    if is_en(lang):
        type_name = "consolidation divergence" if div_type == "consolidation" else "trend divergence"
        strength_name = {"strong": "strong", "medium": "moderate", "weak": "weak"}.get(strength, "")
        description = (f"{strength_name} {type_name} on the {'up' if up else 'down'}-leg: "
                       f"new {'high' if up else 'low'} with weaker force — {forces}")
    else:
        type_name = "盘整背驰" if div_type == "consolidation" else "趋势背驰"
        strength_name = {"strong": "强", "medium": "中", "weak": "弱"}.get(strength, "")
        description = (f"{'上涨' if up else '下跌'}段出现{strength_name}{type_name}：价格创新"
                       f"{'高' if up else '低'}但力度减弱，{forces}")
    return DivergenceResult(is_diverged=True, type=div_type, strength=strength, price_ratio=price_ratio,
                            description=description, volume_ratio=volume_ratio, length_ratio=length_ratio)


def _in_consolidation(prev_leg: Stroke, cur_leg: Stroke, pivots: list | None) -> bool:
    """判断被比较的两个同向段属于「盘整背驰」还是「趋势背驰」。

    缠论定义：趋势 = 至少两个同级别中枢依次排列；盘整 = 单一中枢。据此按「当前段之前
    已形成的中枢数」判定——已形成中枢数 >= 2 → 趋势背驰，否则（0 或 1 个）→ 盘整背驰。

    以中枢计数替代旧的「中枢恰好夹在两段正中间」判据：后者过严，真实行情里几乎所有
    背驰都会被误判成盘整，导致一买 / 一卖被全部抹掉。
    """
    formed = sum(1 for p in (pivots or []) if p.start_time <= cur_leg.start_time)
    return formed < 2


def _find_divergences(legs: list, lang: str = "zh", pivots: list | None = None) -> list[DivergenceResult]:
    """通用背驰检测：对任意有方向的走势段序列（笔或线段）逐段与前一个同向段对比力度。

    返回与 legs 按下标一一对应的列表（下游 zip(strokes, divergences) 依赖此对齐）。
    """
    none_result = DivergenceResult(is_diverged=False, type="none", strength="none",
                                   price_ratio=1.0, description="")
    results: list[DivergenceResult] = []
    for i, leg in enumerate(legs):
        prev_same = legs[i - 2] if i >= 2 and legs[i - 2].direction == leg.direction else None
        if prev_same is None:
            results.append(none_result)
            continue
        new_extreme = (leg.end_price > prev_same.end_price if leg.direction == "up"
                       else leg.end_price < prev_same.end_price)
        if not new_extreme:
            results.append(none_result)
            continue
        results.append(check_divergence(leg, prev_same, _in_consolidation(prev_same, leg, pivots), lang))
    return results


def find_stroke_divergences(
    strokes: list[Stroke], lang: str = "zh", pivots: list | None = None
) -> list[DivergenceResult]:
    """批量检测所有笔的背驰（每笔与前一个同向笔比力度，结合笔级中枢分趋势/盘整）。"""
    return _find_divergences(strokes, lang, pivots)


def find_segment_divergences(
    segments: list, lang: str = "zh", pivots: list | None = None
) -> list[DivergenceResult]:
    """批量检测线段级背驰（每条线段与前一个同向线段比力度，结合线段级中枢分趋势/盘整）。"""
    return _find_divergences(segments, lang, pivots)
