"""威科夫三大定律分析：供求关系、因果关系、量价（努力与结果）。"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.wyckoff.indicators import VolumeStats, bar_spread
from app.services.wyckoff.structure import TradingRange


@dataclass
class LawResult:
    key: str          # "supply_demand" | "cause_effect" | "effort_result"
    name: str         # 中文名
    verdict: str      # 结论（一句话）
    detail: str       # 依据说明


def supply_demand(bars: list[dict], lookback: int = 20) -> LawResult:
    """供求关系：比较近期放量上涨 vs 放量下跌的成交量，判断多空主导。"""
    window = bars[-lookback:] if len(bars) >= lookback else bars
    up_vol = sum(float(b.get("volume", 0) or 0) for b in window if float(b["close"]) >= float(b["open"]))
    down_vol = sum(float(b.get("volume", 0) or 0) for b in window if float(b["close"]) < float(b["open"]))
    total = up_vol + down_vol
    if total <= 0:
        return LawResult("supply_demand", "供求关系", "数据不足", "近期成交量缺失，无法判断供求")
    up_share = up_vol / total
    if up_share >= 0.58:
        verdict = "需求占优（买盘主导）"
    elif up_share <= 0.42:
        verdict = "供给占优（卖盘主导）"
    else:
        verdict = "供求均衡（多空拉锯）"
    detail = f"近 {len(window)} 根 K 线中，上涨日成交量占比 {up_share * 100:.0f}%"
    return LawResult("supply_demand", "供求关系", verdict, detail)


def cause_effect(tr: TradingRange | None) -> LawResult:
    """因果关系：以交易区间宽度作为「原因」，投射突破后的价格目标（简化的量度目标）。"""
    if tr is None or tr.width <= 0:
        return LawResult("cause_effect", "因果关系", "尚无交易区间", "未识别到有效交易区间，无法投射目标")
    width = tr.width
    if tr.kind == "accumulation":
        target = tr.resistance + width
        verdict = f"若向上突破，量度目标约 {target:.2f}"
        detail = (
            f"吸筹区间宽度 {width:.2f}（{tr.support:.2f}–{tr.resistance:.2f}），"
            f"作为上涨动能的「原因」，突破后目标 = 上沿 + 宽度"
        )
    else:
        target = tr.support - width
        verdict = f"若向下跌破，量度目标约 {max(target, 0):.2f}"
        detail = (
            f"派发区间宽度 {width:.2f}（{tr.support:.2f}–{tr.resistance:.2f}），"
            f"作为下跌动能的「原因」，跌破后目标 = 下沿 − 宽度"
        )
    return LawResult("cause_effect", "因果关系", verdict, detail)


def effort_vs_result(bars: list[dict], vstats: VolumeStats, lookback: int = 10) -> LawResult:
    """量价（努力 vs 结果）：近期成交量（努力）与价格进展（结果）是否背离。

    放量却滞涨/滞跌（大努力小结果）预示吸收/派发与潜在反转。
    """
    if len(bars) < lookback + 1:
        return LawResult("effort_result", "量价关系", "数据不足", "K 线不足以评估努力与结果")

    window = bars[-lookback:]
    n = len(window)
    avg_vol = sum(float(b.get("volume", 0) or 0) for b in window) / n
    avg_spread = sum(bar_spread(b) for b in window) / n

    # 最后一根的努力与结果
    last = window[-1]
    last_vol_ratio = vstats.ratio(len(bars) - 1)
    last_spread = bar_spread(last)
    net_progress = float(window[-1]["close"]) - float(window[0]["close"])

    high_effort = last_vol_ratio >= 1.5
    small_result = avg_spread > 0 and last_spread < avg_spread * 0.8

    if high_effort and small_result:
        verdict = "努力大而结果小 → 疑似吸收/派发，警惕反转"
        detail = (
            f"最后一根量比 {last_vol_ratio:.1f}、价差 {last_spread:.2f} 明显小于近 "
            f"{n} 根均值 {avg_spread:.2f}，放量滞涨/滞跌"
        )
    elif net_progress > 0 and last_vol_ratio >= 1.2:
        verdict = "量价配合向上（努力与结果一致）"
        detail = f"近 {n} 根净涨 {net_progress:.2f}，且伴随放量，需求推动有效"
    elif net_progress < 0 and last_vol_ratio >= 1.2:
        verdict = "量价配合向下（努力与结果一致）"
        detail = f"近 {n} 根净跌 {net_progress:.2f}，且伴随放量，供给压制有效"
    else:
        verdict = "量价基本匹配，无明显背离"
        detail = f"近 {n} 根净变动 {net_progress:.2f}，量能 {avg_vol:.0f} 无异常"
    return LawResult("effort_result", "量价关系", verdict, detail)


def analyze_laws(bars: list[dict], vstats: VolumeStats, tr: TradingRange | None) -> list[LawResult]:
    """一次性给出三大定律的分析结果。"""
    return [
        supply_demand(bars),
        cause_effect(tr),
        effort_vs_result(bars, vstats),
    ]
