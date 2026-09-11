"""缠论背驰判断：MACD面积背驰 + 斜率背驰"""
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
    """背驰判断结果"""
    is_diverged: bool
    type: Literal["trend", "consolidation", "none"]  # 趋势背驰 / 盘整背驰 / 无背驰
    strength: Literal["strong", "medium", "weak", "none"]
    area_ratio: float   # 当前段MACD面积/前一段面积（<1 表示背驰）
    description: str
    # 当前段 DIF 峰值 / 前一段 DIF 峰值（黄白线高度比）。<1 表示动能高度也在衰减，
    # 是比单纯面积更强的背驰佐证；>1 说明黄白线创新高、动能其实更强，非真背驰。
    dif_ratio: float = 0.0


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


def _get_stroke_macd_area(stroke: Stroke, macd: MACDData) -> float:
    """计算笔对应时间段内的MACD柱面积（绝对值之和）"""
    start_t, end_t = stroke.start_time, stroke.end_time
    # 找对应时间段的索引
    start_idx, end_idx = None, None
    for i, t in enumerate(macd.times):
        if t >= start_t and start_idx is None:
            start_idx = i
        if t <= end_t:
            end_idx = i

    if start_idx is None or end_idx is None or start_idx > end_idx:
        return 0.0

    return sum(abs(b) for b in macd.bar[start_idx:end_idx + 1])


def _get_stroke_dif_extreme(stroke: Stroke, macd: MACDData) -> float:
    """笔时间段内 DIF（黄白线）的方向性峰值：上升笔取最大 DIF、下降笔取最小 DIF。

    用于「黄白线高度」背驰佐证：顶背驰要求当前上升段 DIF 峰值不高于前一段，
    底背驰要求当前下降段 DIF 谷值不低于前一段。
    """
    start_t, end_t = stroke.start_time, stroke.end_time
    start_idx, end_idx = None, None
    for i, t in enumerate(macd.times):
        if t >= start_t and start_idx is None:
            start_idx = i
        if t <= end_t:
            end_idx = i
    if start_idx is None or end_idx is None or start_idx > end_idx:
        return 0.0
    window = macd.dif[start_idx:end_idx + 1]
    if not window:
        return 0.0
    return max(window) if stroke.direction == "up" else min(window)


def _classify_strength(ratio: float) -> Literal["strong", "medium", "weak", "none"]:
    if ratio >= 1.0:
        return "none"
    if ratio < 0.4:
        return "strong"
    if ratio < 0.7:
        return "medium"
    return "weak"


def check_divergence(
    current_stroke: Stroke,
    compare_stroke: Stroke,
    macd: MACDData,
    in_consolidation: bool = False,
    lang: str = "zh",
) -> DivergenceResult:
    """比较两笔的MACD面积，判断是否背驰。

    current_stroke：当前笔（价格创新高/新低）
    compare_stroke：对比笔（前一个同向笔）
    in_consolidation：是否在中枢内（影响背驰类型判断）
    """
    current_area = _get_stroke_macd_area(current_stroke, macd)
    compare_area = _get_stroke_macd_area(compare_stroke, macd)

    if compare_area == 0:
        return DivergenceResult(
            is_diverged=False,
            type="none",
            strength="none",
            area_ratio=1.0,
            description=pick(lang, "对比段MACD面积为0，无法判断背驰",
                             "Reference-leg MACD area is 0; divergence cannot be assessed"),
        )

    ratio = current_area / compare_area

    # 黄白线（DIF）高度比：方向性峰值之比
    cur_dif = _get_stroke_dif_extreme(current_stroke, macd)
    cmp_dif = _get_stroke_dif_extreme(compare_stroke, macd)
    dif_ratio = (cur_dif / cmp_dif) if cmp_dif != 0 else 1.0

    # 背驰需两个条件同时成立：
    # 1) 价格创新高/新低但 MACD 面积缩小（力度衰减）；
    # 2) 黄白线高度也没有创新高/新低——否则动能其实更强，属「面积因K线数变少而缩小」
    #    的假背驰，予以排除。dif_ratio<1 表示当前段黄白线峰值弱于前段。
    dif_confirms = dif_ratio < 1.0 or cmp_dif == 0
    is_diverged = ratio < 1.0 and dif_confirms

    if not is_diverged:
        if ratio < 1.0 and not dif_confirms:
            reason = pick(
                lang,
                f"MACD面积虽缩小（比值={ratio:.2f}）但黄白线创新高（DIF比={dif_ratio:.2f}），"
                f"动能未衰减，非真背驰",
                f"MACD area shrank (ratio={ratio:.2f}) but DIF made a new extreme "
                f"(DIF ratio={dif_ratio:.2f}); momentum not decaying — not a true divergence",
            )
        else:
            reason = pick(lang, f"MACD面积未缩小（比值={ratio:.2f}），未见背驰",
                          f"MACD area did not shrink (ratio={ratio:.2f}); no divergence")
        return DivergenceResult(
            is_diverged=False,
            type="none",
            strength="none",
            area_ratio=ratio,
            description=reason,
            dif_ratio=dif_ratio,
        )

    div_type = "consolidation" if in_consolidation else "trend"
    strength = _classify_strength(ratio)

    if is_en(lang):
        type_name = "consolidation divergence" if div_type == "consolidation" else "trend divergence"
        dir_name = "up-leg" if current_stroke.direction == "up" else "down-leg"
        strength_name = {"strong": "strong", "medium": "moderate", "weak": "weak"}.get(strength, "")
        description = (
            f"{strength_name} {type_name} on the {dir_name}: MACD area ratio={ratio:.2f}, "
            f"current={current_area:.2f}, reference={compare_area:.2f}"
        )
    else:
        type_name = "盘整背驰" if div_type == "consolidation" else "趋势背驰"
        dir_name = "上涨" if current_stroke.direction == "up" else "下跌"
        strength_name = {"strong": "强", "medium": "中", "weak": "弱"}.get(strength, "")
        description = (
            f"{dir_name}段出现{strength_name}{type_name}：MACD面积比值={ratio:.2f}，"
            f"当前段={current_area:.2f}，对比段={compare_area:.2f}"
        )

    return DivergenceResult(
        is_diverged=True,
        type=div_type,
        strength=strength,
        area_ratio=ratio,
        description=description,
        dif_ratio=dif_ratio,
    )


def _in_consolidation(prev_leg: Stroke, cur_leg: Stroke, pivots: list | None) -> bool:
    """判断被比较的两个同向段属于「盘整背驰」还是「趋势背驰」。

    缠论定义：趋势 = 至少两个同级别中枢依次排列；盘整 = 单一中枢。据此按「当前段之前
    已形成的中枢数」判定——已形成中枢数 >= 2 → 趋势背驰，否则（0 或 1 个）→ 盘整背驰。

    以中枢计数替代旧的「中枢恰好夹在两段正中间」判据：后者过严，真实行情里几乎所有
    背驰都会被误判成盘整，导致一买 / 一卖被全部抹掉。
    """
    formed = sum(1 for p in (pivots or []) if p.start_time <= cur_leg.start_time)
    return formed < 2


def _find_divergences(
    legs: list, macd: MACDData, lang: str = "zh", pivots: list | None = None
) -> list[DivergenceResult]:
    """通用背驰检测：对任意「有方向的走势段」序列（笔或线段）逐段与前一个同向段对比。

    段对象需具备 direction / start_time / end_time / end_price（Stroke、Segment 均满足）。
    结合 pivots 区分趋势背驰 / 盘整背驰（见 _in_consolidation）。
    """
    results: list[DivergenceResult] = []
    none_result = DivergenceResult(
        is_diverged=False, type="none", strength="none", area_ratio=1.0, description=""
    )

    for i, leg in enumerate(legs):
        # 找前一个同向段（段方向严格交替，隔一个即同向）
        prev_same = None
        for j in range(i - 2, -1, -2):
            if j >= 0 and legs[j].direction == leg.direction:
                prev_same = legs[j]
                break

        if prev_same is None:
            results.append(none_result)
            continue

        # 检查价格是否创新高/新低
        if leg.direction == "up" and leg.end_price <= prev_same.end_price:
            results.append(none_result)
            continue
        if leg.direction == "down" and leg.end_price >= prev_same.end_price:
            results.append(none_result)
            continue

        in_consol = _in_consolidation(prev_same, leg, pivots)
        result = check_divergence(leg, prev_same, macd, in_consolidation=in_consol, lang=lang)
        results.append(result)

    return results


def find_stroke_divergences(
    strokes: list[Stroke], macd: MACDData, lang: str = "zh", pivots: list | None = None
) -> list[DivergenceResult]:
    """批量检测所有笔的背驰情况（每笔与前一个同向笔对比，结合笔级中枢分趋势/盘整）。"""
    return _find_divergences(strokes, macd, lang, pivots)


def find_segment_divergences(
    segments: list, macd: MACDData, lang: str = "zh", pivots: list | None = None
) -> list[DivergenceResult]:
    """批量检测线段级背驰（比笔级更高级别，缠论中意义更大）。

    每条线段与前一个同向线段对比 MACD 力度，结合线段级中枢区分趋势 / 盘整背驰。
    """
    return _find_divergences(segments, macd, lang, pivots)
