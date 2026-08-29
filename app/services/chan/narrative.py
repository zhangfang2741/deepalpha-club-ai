"""把缠论技术结构翻译成「大白话」形态解读（中英双语）。

缠论的笔 / 线段 / 中枢 / 背驰对普通用户是黑话。这里做一层规则化的翻译，把
「当前市场在做什么」用业务语言讲清楚：处在什么阶段、价格站在多空争夺区的哪一侧、
量价是否配合、上涨/下跌的力度还足不足。

刻意选择规则化而非 LLM：always-on、免费、即时、离线可测；只**描述现状**不预测涨跌。
文案随请求的 `lang`（zh / en）切换。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.services.chan.bias import VOLUME_WEIGHT
from app.services.chan.i18n import is_en, pick

if TYPE_CHECKING:
    from app.services.chan.analyzer import ChanAnalysisResult


@dataclass
class MarketNarrative:
    """当前形态的大白话解读。"""
    phase: str            # 阶段代码（breakout / uptrend_cont / topping / ...）
    phase_label: str      # 阶段标签（随语言）
    headline: str         # 一句话形态概括
    details: list[str] = field(default_factory=list)  # 分条解读：趋势 / 位置 / 量价 / 动能


def _recent_divergence_dir(result: ChanAnalysisResult) -> str | None:
    """最近一次背驰发生在上升笔还是下降笔上（顶背驰 / 底背驰）。"""
    direction: str | None = None
    for st, dv in zip(result.strokes, result.divergences, strict=False):
        if dv.is_diverged:
            direction = st.direction
    return direction


def _volume_readout(bars: list[dict], lang: str) -> tuple[str, str, float] | None:
    """量价配合解读。

    Returns:
        (量能标签, 大白话句子, 多空分数)，数据不足时 None。
        分数正=偏多、负=偏空，供 analyzer 的多因子加权直接取用——量价的
        方向判断只该有一处，否则两边口径迟早漂移。
    """
    vols = [float(b.get("volume") or 0) for b in bars]
    closes = [float(b["close"]) for b in bars]
    if len(vols) < 12 or all(v == 0 for v in vols):
        return None

    recent = vols[-5:]
    base = vols[-30:-5] if len(vols) >= 35 else vols[:-5]
    if not base:
        return None
    recent_avg = sum(recent) / len(recent)
    base_avg = (sum(base) / len(base)) or 1.0
    ratio = recent_avg / base_avg

    ref = closes[-6] if len(closes) >= 6 else closes[0]
    price_chg = (closes[-1] - ref) / ref if ref else 0.0

    if ratio >= 1.3:
        vol_label = pick(lang, "放量", "rising volume")
    elif ratio <= 0.7:
        vol_label = pick(lang, "缩量", "falling volume")
    else:
        vol_label = pick(lang, "平量", "steady volume")

    rising = price_chg > 0.01
    falling = price_chg < -0.01

    if rising and ratio >= 1.3:
        sentence = pick(lang,
            "近期放量上涨，成交明显放大、资金愿意追，上涨相对健康。",
            "Recent gains came on rising volume — turnover expanded and buyers followed through, a relatively healthy advance.")
        score = VOLUME_WEIGHT
    elif rising and ratio <= 0.7:
        sentence = pick(lang,
            "近期缩量上涨，涨归涨但成交在萎缩，追涨动能不足，需防冲高回落。",
            "Recent gains came on shrinking volume — price rose but turnover faded, momentum is thin, watch for a pullback after spikes.")
        score = -VOLUME_WEIGHT
    elif falling and ratio >= 1.3:
        sentence = pick(lang,
            "近期放量下跌，抛压较重，通常是恐慌或资金离场的信号。",
            "Recent declines came on rising volume — heavy selling pressure, often a sign of panic or money leaving.")
        score = -VOLUME_WEIGHT
    elif falling and ratio <= 0.7:
        sentence = pick(lang,
            "近期缩量下跌，跌势中成交在收敛，抛压趋缓，往往是企稳的前奏。",
            "Recent declines came on shrinking volume — selling pressure is easing, often a prelude to stabilizing.")
        score = VOLUME_WEIGHT
    elif ratio <= 0.7:
        sentence = pick(lang,
            "近期缩量整理，多空都在观望，量能不足以打破当前格局。",
            "Recent consolidation on light volume — both sides are waiting; turnover isn't enough to break the range.")
        score = 0.0
    else:
        sentence = pick(lang,
            "近期量能平稳，价格与成交没有明显背离。",
            "Volume has been steady lately, with no clear divergence between price and turnover.")
        score = 0.0

    return vol_label, sentence, score


def _position_readout(result: ChanAnalysisResult, lang: str) -> tuple[str, str] | None:
    """价格相对最近中枢（多空争夺区）的位置。"""
    if not result.stroke_pivots or not result.merged_candles:
        return None
    p = result.stroke_pivots[-1]
    last = result.merged_candles[-1].close
    if is_en(lang):
        zone = f"the prior tug-of-war price range (pivot {p.zd:.2f}–{p.zg:.2f})"
        if last > p.zg:
            return "above", f"Price {last:.2f} sits above {zone}; bulls have the upper hand for now."
        if last < p.zd:
            return "below", f"Price {last:.2f} has dropped below {zone}; bears have the upper hand for now."
        return "inside", f"Price {last:.2f} is still oscillating within {zone}; a stand-off with no clear direction."
    zone = f"前期反复争夺的价格区间（中枢 {p.zd:.2f}–{p.zg:.2f}）"
    if last > p.zg:
        return "above", f"当前价 {last:.2f} 站在{zone}上方，多方暂时占上风。"
    if last < p.zd:
        return "below", f"当前价 {last:.2f} 跌到{zone}下方，空方暂时占上风。"
    return "inside", f"当前价 {last:.2f} 还在{zone}里来回，多空僵持、方向未定。"


def build_narrative(
    result: ChanAnalysisResult, bars: list[dict], lang: str = "zh"
) -> MarketNarrative | None:
    """综合趋势 / 位置 / 量价 / 动能，产出大白话形态解读。

    数据不足（笔太少、结构没成形）时返回 None，由上层决定是否展示。
    """
    if len(result.strokes) < 3 or not result.merged_candles:
        return None

    trend = result.current_trend or ""
    # current_trend 已按 lang 生成；用与生成端一致的关键词判断方向
    trend_up = ("上升笔" in trend) or ("up-leg" in trend)
    trend_down = ("下降笔" in trend) or ("down-leg" in trend)

    div_dir = _recent_divergence_dir(result)
    pos = _position_readout(result, lang)
    pos_code = pos[0] if pos else None
    vol = _volume_readout(bars, lang)
    en = is_en(lang)

    # ---- 阶段判定（描述当前形态，不预测）----
    if trend_up and div_dir == "up":
        phase = "topping"
        label = pick(lang, "上涨动能减弱", "Momentum fading")
        headline = pick(lang,
            "股价还在往上走，但上涨的力度已经开始减弱，要警惕冲高见顶、转入回调。",
            "Price is still rising, but the push is weakening — watch for a top and a shift into pullback.")
    elif trend_down and div_dir == "down":
        phase = "bottoming"
        label = pick(lang, "下跌动能减弱", "Downside fading")
        headline = pick(lang,
            "跌势还在延续，但下跌的力度在收敛，市场可能正在寻找底部。",
            "The decline continues, but downside force is converging — the market may be searching for a bottom.")
    elif trend_up and pos_code == "above":
        phase = "breakout"
        label = pick(lang, "突破上行", "Breakout")
        headline = pick(lang,
            "股价站上了前期的整理区间，多方掌握主动，目前处在上涨通道里。",
            "Price has cleared the prior range; bulls are in control and it's in an up-channel for now.")
    elif trend_up and pos_code == "inside":
        phase = "range_strong"
        label = pick(lang, "震荡偏强", "Range, leaning up")
        headline = pick(lang,
            "股价在整理区间内偏强运行，多方略占优，但还没有真正突破。",
            "Price is holding firm inside the range with bulls slightly ahead, but hasn't truly broken out yet.")
    elif trend_down and pos_code == "below":
        phase = "breakdown"
        label = pick(lang, "破位下行", "Breakdown")
        headline = pick(lang,
            "股价跌破了前期的整理区间，空方主导，目前处在下跌通道里。",
            "Price has broken below the prior range; bears are in control and it's in a down-channel for now.")
    elif pos_code == "inside":
        phase = "range"
        label = pick(lang, "区间震荡", "Range-bound")
        headline = pick(lang,
            "股价在一个整理区间里反复拉锯，多空暂时僵持，方向还没选出来。",
            "Price is see-sawing within a range; a stand-off with direction not yet chosen.")
    elif trend_up:
        phase = "uptrend"
        label = pick(lang, "上升趋势", "Uptrend")
        headline = pick(lang, "股价整体震荡向上，多方目前占据主动。",
                        "Price is grinding higher overall; bulls have the initiative for now.")
    elif trend_down:
        phase = "downtrend"
        label = pick(lang, "下降趋势", "Downtrend")
        headline = pick(lang, "股价整体震荡向下，空方目前占据主动。",
                        "Price is grinding lower overall; bears have the initiative for now.")
    else:
        phase = "unclear"
        label = pick(lang, "方向不明", "Unclear")
        headline = pick(lang,
            "当前结构还不清晰，多空力量接近，方向有待后续K线明朗。",
            "The structure isn't clear yet; the two sides are evenly matched and direction awaits later bars.")

    # ---- 分条解读 ----
    details: list[str] = []

    if trend_up:
        details.append(pick(lang, "短期节奏（笔）向上，处于上升的一段中。",
                            "The short-term rhythm (stroke) points up — in a rising leg."))
    elif trend_down:
        details.append(pick(lang, "短期节奏（笔）向下，处于下跌的一段中。",
                            "The short-term rhythm (stroke) points down — in a falling leg."))
    if result.segments:
        seg = result.segments[-1]
        if en:
            big = "up" if seg.direction == "up" else "down"
            details.append(f"The larger-degree direction (segment) is {big}, so the medium-term "
                           f"trend leans {'bullish' if seg.direction == 'up' else 'bearish'}.")
        else:
            big = "向上" if seg.direction == "up" else "向下"
            details.append(f"更大级别的方向（线段）{big}，代表中期趋势偏"
                           f"{'多' if seg.direction == 'up' else '空'}。")

    if pos:
        details.append(pos[1])
    if vol:
        details.append(vol[1])

    if div_dir == "up" and trend_up:
        details.append(pick(lang,
            "上涨过程中出现了力度背离（顶背驰）：价格创新高但动能没跟上，是见顶的常见前兆。",
            "A momentum divergence appeared during the advance (top divergence): price made new highs but "
            "momentum didn't follow — a common precursor to a top."))
    elif div_dir == "down" and trend_down:
        details.append(pick(lang,
            "下跌过程中出现了力度背离（底背驰）：价格创新低但动能在减弱，是筑底的常见前兆。",
            "A momentum divergence appeared during the decline (bottom divergence): price made new lows but "
            "momentum weakened — a common precursor to a bottom."))

    return MarketNarrative(phase=phase, phase_label=label, headline=headline, details=details)
