"""缠论分析主协调器：整合分型→笔→线段→中枢→背驰→买卖点"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logging import logger
from app.services.chan.divergence import DivergenceResult, MACDData, calc_macd, find_stroke_divergences
from app.services.chan.fractal import Fractal, MergedCandle, find_fractals, merge_candles
from app.services.chan.pivot import Pivot, find_segment_pivots, find_stroke_pivots
from app.services.chan.segment import Segment, find_segments
from app.services.chan.signals import Signal, generate_all_signals
from app.services.chan.stroke import Stroke, find_strokes


@dataclass
class Recommendation:
    """当前操作建议（综合趋势 / 信号 / 背驰 / 中枢位置 / 线段方向）"""
    action: str          # buy / sell / hold_bullish / hold_bearish / watch
    action_label: str    # 中文操作标签
    bias: str            # bullish / bearish / neutral
    reasons: list[str] = field(default_factory=list)   # 依据（为什么这样建议）
    caveats: list[str] = field(default_factory=list)   # 风险提示


@dataclass
class ChanAnalysisResult:
    """缠论完整分析结果"""
    symbol: str
    bars_count: int

    # 各层分析结果
    merged_candles: list[MergedCandle] = field(default_factory=list)
    fractals: list[Fractal] = field(default_factory=list)
    strokes: list[Stroke] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    stroke_pivots: list[Pivot] = field(default_factory=list)
    segment_pivots: list[Pivot] = field(default_factory=list)
    divergences: list[DivergenceResult] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    macd: MACDData | None = None

    # 当前市场状态摘要
    current_trend: str = ""
    latest_signal: Signal | None = None
    summary: str = ""
    recommendation: Recommendation | None = None

    @property
    def buy_signals(self) -> list[Signal]:
        return [s for s in self.signals if s.is_buy]

    @property
    def sell_signals(self) -> list[Signal]:
        return [s for s in self.signals if not s.is_buy]

    @property
    def recent_signals(self) -> list[Signal]:
        """最近10个信号"""
        return self.signals[-10:]


class ChanAnalyzer:
    """缠论分析器"""

    def analyze(self, symbol: str, bars: list[dict], *, min_gap: int = 4) -> ChanAnalysisResult:
        """对K线数据执行完整缠论分析。

        bars: list of {time, open, high, low, close, volume}
        min_gap: 笔成立所需的最小分型间隔（合并K线数 - 1），默认 4（缠论新笔标准）
        """
        logger.info("chan_analysis_start", symbol=symbol, bars=len(bars), min_gap=min_gap)

        result = ChanAnalysisResult(symbol=symbol, bars_count=len(bars))

        if len(bars) < 10:
            result.summary = "K线数据不足（最少需要10根），无法进行缠论分析"
            return result

        # 1. 包含关系处理
        result.merged_candles = merge_candles(bars)
        logger.debug("chan_merged_candles", count=len(result.merged_candles))

        # 2. 分型识别
        result.fractals = find_fractals(result.merged_candles)
        logger.debug("chan_fractals", count=len(result.fractals))

        if len(result.fractals) < 2:
            result.summary = f"分型不足（仅{len(result.fractals)}个），行情可能处于单边走势"
            return result

        # 3. 笔识别
        result.strokes = find_strokes(result.fractals, min_gap=min_gap)
        logger.debug("chan_strokes", count=len(result.strokes))

        if len(result.strokes) < 3:
            result.summary = f"笔数量不足（仅{len(result.strokes)}笔），无法识别线段和中枢"
            result.current_trend = self._infer_trend_from_strokes(result.strokes)
            return result

        # 4. 线段识别
        result.segments = find_segments(result.strokes)
        logger.debug("chan_segments", count=len(result.segments))

        # 5. 中枢识别（笔级别）
        result.stroke_pivots = find_stroke_pivots(result.strokes)

        # 5b. 中枢识别（线段级别）
        if len(result.segments) >= 3:
            result.segment_pivots = find_segment_pivots(result.segments)
        logger.debug(
            "chan_pivots",
            stroke_pivots=len(result.stroke_pivots),
            segment_pivots=len(result.segment_pivots),
        )

        # 6. MACD计算
        result.macd = calc_macd(bars)

        # 7. 背驰判断
        result.divergences = find_stroke_divergences(result.strokes, result.macd)
        diverged_count = sum(1 for d in result.divergences if d.is_diverged)
        logger.debug("chan_divergences", total=len(result.divergences), diverged=diverged_count)

        # 8. 买卖点生成（使用笔级别中枢）
        all_pivots = result.stroke_pivots + result.segment_pivots
        all_pivots.sort(key=lambda p: p.start_time)
        result.signals = generate_all_signals(result.strokes, result.divergences, all_pivots)
        logger.debug("chan_signals", count=len(result.signals))

        # 9. 当前状态摘要
        result.current_trend = self._infer_trend_from_strokes(result.strokes)
        result.latest_signal = result.signals[-1] if result.signals else None
        result.summary = self._build_summary(result)
        result.recommendation = self._build_recommendation(result)

        logger.info(
            "chan_analysis_complete",
            symbol=symbol,
            strokes=len(result.strokes),
            pivots=len(result.stroke_pivots),
            signals=len(result.signals),
        )
        return result

    def _infer_trend_from_strokes(self, strokes: list[Stroke]) -> str:
        if not strokes:
            return "数据不足"
        last = strokes[-1]
        if last.direction == "up":
            return "当前处于上升笔末端"
        return "当前处于下降笔末端"

    def _build_recommendation(self, r: ChanAnalysisResult) -> Recommendation:
        """综合缠论各维度，给出当前操作建议及依据。

        判断顺序：近期买卖点信号优先；无新鲜信号时看趋势 + 背驰；
        再以中枢位置、线段方向补充佐证。
        """
        reasons: list[str] = []
        caveats: list[str] = []

        # 最近一个背驰及方向：上升笔背驰=顶背驰，下降笔背驰=底背驰
        recent_div_dir: str | None = None
        for st, dv in zip(r.strokes, r.divergences, strict=False):
            if dv.is_diverged:
                recent_div_dir = st.direction

        # 信号新鲜度：落在最近两笔区间内的信号才视为当前有效
        fresh_cutoff = r.strokes[-2].start_time if len(r.strokes) >= 2 else ""
        latest = r.latest_signal
        signal_fresh = bool(latest and latest.time >= fresh_cutoff)

        last_price = r.merged_candles[-1].close if r.merged_candles else 0.0
        trend = r.current_trend

        if signal_fresh and latest is not None:
            if latest.is_buy:
                action, label, bias = "buy", "技术面偏多，可关注买入机会", "bullish"
            else:
                action, label, bias = "sell", "技术面偏空，可关注卖出/减仓", "bearish"
            reasons.append(
                f"最近触发{latest.label}（{latest.strength}强度，{latest.time}）：{latest.description}"
            )
        elif "上升笔" in trend:
            if recent_div_dir == "up":
                action, label, bias = "hold_bearish", "上涨或近尾声，偏谨慎观望", "bearish"
                reasons.append("当前处于上升笔末端，且最近出现顶背驰，上涨动能衰竭，警惕回调")
            else:
                action, label, bias = "hold_bullish", "趋势向上，持有观望", "bullish"
                reasons.append("当前处于上升笔末端，暂无顶背驰，上升趋势延续中，留意是否见顶")
        elif "下降笔" in trend:
            if recent_div_dir == "down":
                action, label, bias = "hold_bullish", "下跌或近尾声，关注反弹", "bullish"
                reasons.append("当前处于下降笔末端，且最近出现底背驰，下跌动能衰竭，可能反弹")
            else:
                action, label, bias = "hold_bearish", "趋势向下，谨慎观望", "bearish"
                reasons.append("当前处于下降笔末端，暂无底背驰，下跌可能延续")
        else:
            action, label, bias = "watch", "结构不明，建议观望", "neutral"
            reasons.append("当前走势结构尚不明确，建议观望等待明确信号")

        # 当前价相对最近中枢的位置
        if r.stroke_pivots:
            p = r.stroke_pivots[-1]
            if last_price > p.zg:
                reasons.append(f"当前价 {last_price:.2f} 站上最近中枢上沿 ZG（{p.zg:.2f}），多头占优")
            elif last_price < p.zd:
                reasons.append(f"当前价 {last_price:.2f} 跌破最近中枢下沿 ZD（{p.zd:.2f}），空头占优")
            else:
                reasons.append(
                    f"当前价 {last_price:.2f} 仍在最近中枢（{p.zd:.2f}–{p.zg:.2f}）内，多空交战、方向待选"
                )

        # 最近线段方向佐证大级别趋势
        if r.segments:
            seg = r.segments[-1]
            reasons.append(
                f"最近线段方向{'向上' if seg.direction == 'up' else '向下'}，"
                f"大级别趋势{'偏多' if seg.direction == 'up' else '偏空'}"
            )

        caveats.append("缠论分型 / 笔需后续K线确认，信号存在滞后性")
        caveats.append("本建议为技术面参考，不构成投资建议，请结合基本面与风险自行决策")

        return Recommendation(action=action, action_label=label, bias=bias, reasons=reasons, caveats=caveats)

    def _build_summary(self, r: ChanAnalysisResult) -> str:
        parts = [
            f"共识别 {len(r.merged_candles)} 根合并K线，"
            f"{len(r.fractals)} 个分型，{len(r.strokes)} 笔，"
            f"{len(r.segments)} 条线段，"
            f"{len(r.stroke_pivots)} 个笔级中枢，"
            f"{len(r.segment_pivots)} 个线段级中枢。",
        ]

        if r.current_trend:
            parts.append(r.current_trend + "。")

        buy_signals = [s for s in r.signals if s.is_buy]
        sell_signals = [s for s in r.signals if not s.is_buy]
        if r.signals:
            parts.append(
                f"共发现 {len(buy_signals)} 个买点信号、{len(sell_signals)} 个卖点信号。"
            )

        if r.latest_signal:
            s = r.latest_signal
            parts.append(
                f"最近信号：{s.label}（{s.strength}强度），时间={s.time}，价格={s.price:.2f}。"
            )

        return "".join(parts)
