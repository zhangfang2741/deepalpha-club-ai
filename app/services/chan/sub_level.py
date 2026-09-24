"""次级别确认：日线定方向 × 30 分钟找买卖点的联动判定（纯函数，不做 IO）。

- 日线方向取日线分析的形态倾向 recommendation.bias（即详情页「技术面偏强/偏弱」
  的多因子加权结论），不另起一套标准。
- 30 分钟信号取「最近 2 个交易日」（30 分钟 K 线中最后两个不同日期）内的买卖点；
  同时有买点和卖点时以最新的一个为准。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from app.services.chan.i18n import is_en, pick

if TYPE_CHECKING:
    from app.services.chan.analyzer import ChanAnalysisResult
    from app.services.chan.signals import Signal

Verdict = Literal["resonance_buy", "resonance_sell", "counter_trend", "waiting", "unavailable"]

_RECENT_TRADING_DAYS = 2

_VERDICT_LABELS: dict[str, tuple[str, str]] = {
    "resonance_buy": ("共振买点", "Aligned buy"),
    "resonance_sell": ("共振卖点", "Aligned sell"),
    "counter_trend": ("逆势信号", "Counter-trend signal"),
    "waiting": ("等待次级别信号", "Waiting for a lower-level signal"),
    "unavailable": ("次级别暂不可用", "Lower level unavailable"),
}

_STRENGTH_ZH = {"strong": "强", "medium": "中", "weak": "弱"}


@dataclass
class SubLevelResult:
    daily_bias: str                 # bullish / bearish / neutral
    daily_bias_label: str           # 日线形态倾向文案（与详情页一致）
    verdict: Verdict
    verdict_label: str
    detail: str
    sub_freq: str = "30min"
    recent_signals: list[Signal] = field(default_factory=list)


def _recent_signals(sub: ChanAnalysisResult) -> list[Signal]:
    days = sorted({c.time[:10] for c in sub.merged_candles})
    if not days:
        return []
    cutoff = days[-_RECENT_TRADING_DAYS] if len(days) >= _RECENT_TRADING_DAYS else days[0]
    return sorted((s for s in sub.signals if s.time[:10] >= cutoff), key=lambda s: s.time)


def _detail(verdict: Verdict, daily_label: str, latest: Signal | None, lang: str) -> str:
    en = is_en(lang)
    if verdict == "unavailable":
        return pick(lang, "30 分钟数据暂时无法获取或不足以分析，先以日线结论为准。",
                    "30-minute data is unavailable or too short to analyze; rely on the daily view for now.")
    if latest is None:
        return pick(lang, f"日线{daily_label}；近两个交易日 30 分钟级别没有出现买卖点，等待次级别信号。",
                    f"Daily: {daily_label}. No 30-minute buy/sell point in the last two trading days — "
                    f"waiting for a lower-level signal.")
    sig = (f"{latest.label} ({latest.strength}) at {latest.time}" if en
           else f"{latest.time} 出现{latest.label}（{_STRENGTH_ZH.get(latest.strength, '')}）")
    if verdict == "resonance_buy":
        return pick(lang, f"日线{daily_label}，30 分钟 {sig}：大方向与次级别买点一致。",
                    f"Daily: {daily_label}; 30-minute {sig} — the lower-level buy agrees with the larger trend.")
    if verdict == "resonance_sell":
        return pick(lang, f"日线{daily_label}，30 分钟 {sig}：大方向与次级别卖点一致。",
                    f"Daily: {daily_label}; 30-minute {sig} — the lower-level sell agrees with the larger trend.")
    if verdict == "counter_trend":
        kind = pick(lang, "反弹" if latest.is_buy else "回调", "bounce" if latest.is_buy else "pullback")
        return pick(lang, f"日线{daily_label}，但 30 分钟 {sig}，与日线方向相反，更可能只是次级别的{kind}。",
                    f"Daily: {daily_label}, but 30-minute {sig} runs against it — more likely just a "
                    f"lower-level {kind}.")
    return pick(lang, f"日线{daily_label}，大方向不明；30 分钟 {sig} 仅供参考。",
                f"Daily: {daily_label}, no clear direction; the 30-minute {sig} is for reference only.")


def build_sub_level(
    daily: ChanAnalysisResult, sub: ChanAnalysisResult | None, lang: str = "zh",
) -> SubLevelResult:
    """联动判定：日线倾向 + 30 分钟近期买卖点 → 共振 / 逆势 / 等待 / 不可用。"""
    rec = daily.recommendation
    bias = rec.bias if rec else "neutral"
    daily_label = rec.action_label if rec else pick(lang, "方向未明", "direction unclear")

    recent: list[Signal] = []
    latest: Signal | None = None
    if sub is None or not sub.strokes:
        verdict: Verdict = "unavailable"
    else:
        recent = _recent_signals(sub)
        latest = recent[-1] if recent else None
        if latest is None or bias == "neutral":
            verdict = "waiting"
        elif latest.is_buy == (bias == "bullish"):
            verdict = "resonance_buy" if latest.is_buy else "resonance_sell"
        else:
            verdict = "counter_trend"

    zh, en = _VERDICT_LABELS[verdict]
    return SubLevelResult(
        daily_bias=bias,
        daily_bias_label=daily_label,
        verdict=verdict,
        verdict_label=pick(lang, zh, en),
        detail=_detail(verdict, daily_label, latest, lang),
        recent_signals=recent,
    )
