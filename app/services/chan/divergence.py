"""缠论背驰判断：MACD面积背驰 + 斜率背驰"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
    使用标准EMA公式：DIF = EMA(close, fast) - EMA(close, slow)
    DEA = EMA(DIF, signal)，MACD = 2*(DIF-DEA)
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
            description="对比段MACD面积为0，无法判断背驰",
        )

    ratio = current_area / compare_area

    # 价格新高/新低但MACD面积缩小 → 背驰
    is_diverged = ratio < 1.0

    if not is_diverged:
        return DivergenceResult(
            is_diverged=False,
            type="none",
            strength="none",
            area_ratio=ratio,
            description=f"MACD面积未缩小（比值={ratio:.2f}），未见背驰",
        )

    div_type = "consolidation" if in_consolidation else "trend"
    strength = _classify_strength(ratio)

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
    )


def find_stroke_divergences(strokes: list[Stroke], macd: MACDData) -> list[DivergenceResult]:
    """批量检测所有笔的背驰情况。
    每笔与前一个同向笔对比。
    """
    results: list[DivergenceResult] = []
    none_result = DivergenceResult(
        is_diverged=False, type="none", strength="none", area_ratio=1.0, description=""
    )

    for i, stroke in enumerate(strokes):
        # 找前一个同向笔
        prev_same = None
        for j in range(i - 2, -1, -2):  # 每隔两笔找同向
            if j >= 0 and strokes[j].direction == stroke.direction:
                prev_same = strokes[j]
                break

        if prev_same is None:
            results.append(none_result)
            continue

        # 检查价格是否创新高/新低
        if stroke.direction == "up" and stroke.end_price <= prev_same.end_price:
            results.append(none_result)
            continue
        if stroke.direction == "down" and stroke.end_price >= prev_same.end_price:
            results.append(none_result)
            continue

        result = check_divergence(stroke, prev_same, macd)
        results.append(result)

    return results
