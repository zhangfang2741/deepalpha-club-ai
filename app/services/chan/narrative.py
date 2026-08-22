"""把缠论技术结构翻译成「大白话」形态解读。

缠论的笔 / 线段 / 中枢 / 背驰对普通用户是黑话。这里做一层规则化的翻译，把
「当前市场在做什么」用业务语言讲清楚：处在什么阶段、价格站在多空争夺区的哪一侧、
量价是否配合、上涨/下跌的力度还足不足。

刻意选择规则化而非 LLM：
- always-on、免费、即时，且离线可测（缠论本身就是确定性的几何结构）；
- 只**描述现状**，不预测涨跌——措辞一律用「通常 / 意味着 / 需警惕」这类有边界的说法。

量价数据来自原始 bars（合并K线丢了 volume，但保留了 raw_start/raw_end，且 analyze()
本身也拿得到原始 bars），所以这里直接吃 bars 算成交量。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.chan.analyzer import ChanAnalysisResult


@dataclass
class MarketNarrative:
    """当前形态的大白话解读。"""
    phase: str            # 阶段代码（breakout / uptrend_cont / topping / ...）
    phase_label: str      # 阶段中文标签（突破上行 / 上涨中继 / ...）
    headline: str         # 一句话形态概括
    details: list[str] = field(default_factory=list)  # 分条解读：趋势 / 位置 / 量价 / 动能


def _recent_divergence_dir(result: ChanAnalysisResult) -> str | None:
    """最近一次背驰发生在上升笔还是下降笔上（顶背驰 / 底背驰）。"""
    direction: str | None = None
    for st, dv in zip(result.strokes, result.divergences, strict=False):
        if dv.is_diverged:
            direction = st.direction
    return direction


def _volume_readout(bars: list[dict]) -> tuple[str, str] | None:
    """量价配合解读。

    Returns:
        (量能标签, 大白话句子)，数据不足时 None。
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

    # 近 5 根的价格方向
    ref = closes[-6] if len(closes) >= 6 else closes[0]
    price_chg = (closes[-1] - ref) / ref if ref else 0.0

    if ratio >= 1.3:
        vol_label = "放量"
    elif ratio <= 0.7:
        vol_label = "缩量"
    else:
        vol_label = "平量"

    rising = price_chg > 0.01
    falling = price_chg < -0.01

    # 量价配合矩阵：只描述含义，不下结论
    if rising and vol_label == "放量":
        sentence = "近期放量上涨，成交明显放大、资金愿意追，上涨相对健康。"
    elif rising and vol_label == "缩量":
        sentence = "近期缩量上涨，涨归涨但成交在萎缩，追涨动能不足，需防冲高回落。"
    elif falling and vol_label == "放量":
        sentence = "近期放量下跌，抛压较重，通常是恐慌或资金离场的信号。"
    elif falling and vol_label == "缩量":
        sentence = "近期缩量下跌，跌势中成交在收敛，抛压趋缓，往往是企稳的前奏。"
    elif vol_label == "缩量":
        sentence = "近期缩量整理，多空都在观望，量能不足以打破当前格局。"
    else:
        sentence = "近期量能平稳，价格与成交没有明显背离。"

    return vol_label, sentence


def _position_readout(result: ChanAnalysisResult) -> tuple[str, str] | None:
    """价格相对最近中枢（多空争夺区）的位置。

    Returns:
        (位置代码 above/inside/below, 大白话句子)，无中枢时 None。
    """
    if not result.stroke_pivots or not result.merged_candles:
        return None
    p = result.stroke_pivots[-1]
    last = result.merged_candles[-1].close
    zone = f"前期反复争夺的价格区间（中枢 {p.zd:.2f}–{p.zg:.2f}）"
    if last > p.zg:
        return "above", f"当前价 {last:.2f} 站在{zone}上方，多方暂时占上风。"
    if last < p.zd:
        return "below", f"当前价 {last:.2f} 跌到{zone}下方，空方暂时占上风。"
    return "inside", f"当前价 {last:.2f} 还在{zone}里来回，多空僵持、方向未定。"


def build_narrative(result: ChanAnalysisResult, bars: list[dict]) -> MarketNarrative | None:
    """综合趋势 / 位置 / 量价 / 动能，产出大白话形态解读。

    数据不足（笔太少、结构没成形）时返回 None，由上层决定是否展示。
    """
    if len(result.strokes) < 3 or not result.merged_candles:
        return None

    trend = result.current_trend or ""
    trend_up = "上升笔" in trend
    trend_down = "下降笔" in trend

    div_dir = _recent_divergence_dir(result)
    pos = _position_readout(result)
    pos_code = pos[0] if pos else None
    vol = _volume_readout(bars)

    # ---- 阶段判定（描述当前形态，不预测）----
    if trend_up and div_dir == "up":
        phase, label = "topping", "上涨动能衰减"
        headline = "股价还在往上走，但上涨的力度已经开始减弱，要警惕冲高见顶、转入回调。"
    elif trend_down and div_dir == "down":
        phase, label = "bottoming", "下跌动能衰减"
        headline = "跌势还在延续，但下跌的力度在收敛，市场可能正在寻找底部。"
    elif trend_up and pos_code == "above":
        phase, label = "breakout", "突破上行"
        headline = "股价站上了前期的整理区间，多方掌握主动，目前处在上涨通道里。"
    elif trend_up and pos_code == "inside":
        phase, label = "range_strong", "震荡偏强"
        headline = "股价在整理区间内偏强运行，多方略占优，但还没有真正突破。"
    elif trend_down and pos_code == "below":
        phase, label = "breakdown", "破位下行"
        headline = "股价跌破了前期的整理区间，空方主导，目前处在下跌通道里。"
    elif pos_code == "inside":
        phase, label = "range", "区间震荡"
        headline = "股价在一个整理区间里反复拉锯，多空暂时僵持，方向还没选出来。"
    elif trend_up:
        phase, label = "uptrend", "上升趋势"
        headline = "股价整体震荡向上，多方目前占据主动。"
    elif trend_down:
        phase, label = "downtrend", "下降趋势"
        headline = "股价整体震荡向下，空方目前占据主动。"
    else:
        phase, label = "unclear", "方向不明"
        headline = "当前结构还不清晰，多空力量接近，建议观望等待方向明朗。"

    # ---- 分条解读 ----
    details: list[str] = []

    # 趋势（笔级 + 大级别线段）
    if trend_up:
        details.append("短期节奏（笔）向上，处于上升的一段中。")
    elif trend_down:
        details.append("短期节奏（笔）向下，处于下跌的一段中。")
    if result.segments:
        seg = result.segments[-1]
        big = "向上" if seg.direction == "up" else "向下"
        details.append(f"更大级别的方向（线段）{big}，代表中期趋势偏{'多' if seg.direction == 'up' else '空'}。")

    # 位置
    if pos:
        details.append(pos[1])

    # 量价
    if vol:
        details.append(vol[1])

    # 动能 / 背驰：只在与当前趋势一致时才提，避免「突破上行」却挂着历史底背驰这类
    # 让人困惑的错配（阶段判定用的也是同一口径）。
    if div_dir == "up" and trend_up:
        details.append("上涨过程中出现了力度背离（顶背驰）：价格创新高但动能没跟上，是见顶的常见前兆。")
    elif div_dir == "down" and trend_down:
        details.append("下跌过程中出现了力度背离（底背驰）：价格创新低但动能在减弱，是筑底的常见前兆。")

    return MarketNarrative(phase=phase, phase_label=label, headline=headline, details=details)
