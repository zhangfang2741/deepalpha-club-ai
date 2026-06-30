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

    def analyze(self, symbol: str, bars: list[dict]) -> ChanAnalysisResult:
        """对K线数据执行完整缠论分析。

        bars: list of {time, open, high, low, close, volume}
        """
        logger.info("chan_analysis_start", symbol=symbol, bars=len(bars))

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
        result.strokes = find_strokes(result.fractals)
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
