"""次级别确认：大级别定方向 × 次级别找买卖点的联动判定（纯函数，不做 IO）。

级别逐级递推（缠论区间套）：日线 → 30 分钟、周线 → 日线，不跨级。
- 大级别方向取其分析的形态倾向 recommendation.bias（即详情页「技术面偏强/偏弱」
  的多因子加权结论），不另起一套标准。
- 次级别信号取「最近」窗口内的买卖点，窗口按级别比例放大：日线配 30 分钟看最近
  2 个交易日（30 分钟 K 线中最后两个不同日期），周线配日线看最近两周（14 个自然日）；
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

ParentFreq = Literal["daily", "weekly"]


@dataclass(frozen=True)
class LevelPair:
    """一组大级别 → 次级别配对及其文案。"""

    parent: ParentFreq
    child: str                      # 次级别周期（fetch_kline 的 freq）
    recent_sessions: int = 0        # 按「最后 N 个不同日期」取最近窗口（分钟线用）
    recent_calendar_days: int = 0   # 按「最后一根往前 N 个自然日」取最近窗口（日线用）
    fetch_days: int = 40            # 次级别取数窗口（自然日，含预热）
    parent_zh: str = "日线"
    parent_en: str = "Daily"
    child_zh: str = "30 分钟"
    child_en: str = "30-minute"
    recent_zh: str = "近两个交易日"
    recent_en: str = "in the last two trading days"


LEVEL_PAIRS: dict[str, LevelPair] = {
    # 30 分钟取数约 27 个交易日，足够形成次级别的笔与中枢；Yahoo 分钟线上限 60 天
    "daily": LevelPair(parent="daily", child="30min", recent_sessions=2, fetch_days=40),
    # 日线作次级别要有足够预热（czsc 需积累若干笔才出买卖点），与详情页日线预热同量级
    "weekly": LevelPair(parent="weekly", child="daily", recent_calendar_days=14, fetch_days=270,
                        parent_zh="周线", parent_en="Weekly", child_zh="日线", child_en="daily",
                        recent_zh="近两周", recent_en="in the last two weeks"),
}

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
    parent_freq: str = "daily"
    recent_signals: list[Signal] = field(default_factory=list)


def _recent_signals(sub: ChanAnalysisResult, pair: LevelPair) -> list[Signal]:
    days = sorted({c.time[:10] for c in sub.merged_candles})
    if not days:
        return []
    if pair.recent_calendar_days:
        from datetime import date, timedelta

        last = date.fromisoformat(days[-1])
        cutoff = (last - timedelta(days=pair.recent_calendar_days - 1)).isoformat()
    else:
        n = pair.recent_sessions
        cutoff = days[-n] if len(days) >= n else days[0]
    return sorted((s for s in sub.signals if s.time[:10] >= cutoff), key=lambda s: s.time)


def _detail(verdict: Verdict, daily_label: str, latest: Signal | None, lang: str,
            pair: LevelPair = LEVEL_PAIRS["daily"]) -> str:
    en = is_en(lang)
    pz, pe, cz, ce = pair.parent_zh, pair.parent_en, pair.child_zh, pair.child_en
    if verdict == "unavailable":
        return pick(lang, f"{cz}数据暂时无法获取或不足以分析，先以{pz}结论为准。",
                    f"{ce.capitalize()} data is unavailable or too short to analyze; "
                    f"rely on the {pe.lower()} view for now.")
    if latest is None:
        return pick(lang, f"{pz}{daily_label}；{pair.recent_zh}{cz}级别没有出现买卖点，等待次级别信号。",
                    f"{pe}: {daily_label}. No {ce} buy/sell point {pair.recent_en} — "
                    f"waiting for a lower-level signal.")
    sig = (f"{latest.label} ({latest.strength}) at {latest.time}" if en
           else f"{latest.time} 出现{latest.label}（{_STRENGTH_ZH.get(latest.strength, '')}）")
    if verdict == "resonance_buy":
        return pick(lang, f"{pz}{daily_label}，{cz} {sig}：大方向与次级别买点一致。",
                    f"{pe}: {daily_label}; {ce} {sig} — the lower-level buy agrees with the larger trend.")
    if verdict == "resonance_sell":
        return pick(lang, f"{pz}{daily_label}，{cz} {sig}：大方向与次级别卖点一致。",
                    f"{pe}: {daily_label}; {ce} {sig} — the lower-level sell agrees with the larger trend.")
    if verdict == "counter_trend":
        kind = pick(lang, "反弹" if latest.is_buy else "回调", "bounce" if latest.is_buy else "pullback")
        gap = " " if cz[:1].isdigit() else ""  # 「但 30 分钟」留空格，「但日线」不留
        return pick(lang, f"{pz}{daily_label}，但{gap}{cz} {sig}，与{pz}方向相反，更可能只是次级别的{kind}。",
                    f"{pe}: {daily_label}, but {ce} {sig} runs against it — more likely just a "
                    f"lower-level {kind}.")
    return pick(lang, f"{pz}{daily_label}，大方向不明；{cz} {sig} 仅供参考。",
                f"{pe}: {daily_label}, no clear direction; the {ce} {sig} is for reference only.")


def build_sub_level(
    daily: ChanAnalysisResult, sub: ChanAnalysisResult | None, lang: str = "zh",
    parent_freq: str = "daily",
) -> SubLevelResult:
    """联动判定：大级别倾向 + 次级别近期买卖点 → 共振 / 逆势 / 等待 / 不可用。

    daily 为大级别分析结果（参数名沿用，周线配对时传周线结果）。
    """
    pair = LEVEL_PAIRS.get(parent_freq, LEVEL_PAIRS["daily"])
    rec = daily.recommendation
    bias = rec.bias if rec else "neutral"
    daily_label = rec.action_label if rec else pick(lang, "方向未明", "direction unclear")

    recent: list[Signal] = []
    latest: Signal | None = None
    if sub is None or not sub.strokes:
        verdict: Verdict = "unavailable"
    else:
        recent = _recent_signals(sub, pair)
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
        detail=_detail(verdict, daily_label, latest, lang, pair),
        sub_freq=pair.child,
        parent_freq=pair.parent,
        recent_signals=recent,
    )
