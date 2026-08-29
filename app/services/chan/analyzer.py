"""缠论分析主协调器：整合分型→笔→线段→中枢→背驰→买卖点"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logging import logger
from app.services.chan.bias import (
    DIVERGENCE_WEIGHT,
    PIVOT_WEIGHT,
    SEGMENT_WEIGHT,
    SIGNAL_WEIGHT,
    STRONG_BIAS_THRESHOLD,
    STROKE_WEIGHT,
    UNCONFIRMED_DISCOUNT,
    BiasFactor,
    score_to_bias,
)
from app.services.chan.divergence import DivergenceResult, MACDData, calc_macd, find_stroke_divergences
from app.services.chan.fractal import Fractal, MergedCandle, find_fractals, merge_candles
from app.services.chan.i18n import is_en, pick
from app.services.chan.narrative import MarketNarrative, _volume_readout, build_narrative
from app.services.chan.pivot import Pivot, find_segment_pivots, find_stroke_pivots
from app.services.chan.segment import Segment, find_segments
from app.services.chan.signals import Signal, generate_all_signals
from app.services.chan.stroke import Stroke, find_strokes


@dataclass
class Recommendation:
    """当前技术形态倾向（综合趋势 / 信号 / 背驰 / 中枢位置 / 线段方向）。

    仅描述技术面强弱，不含操作建议——措辞刻意避开「买入/卖出」等动作词，
    以免被认定为荐股 / 投资咨询。
    """
    action: str          # buy / sell / hold_bullish / hold_bearish / watch（内部用，不展示）
    action_label: str    # 中文技术形态标签（对外展示）
    bias: str            # bullish / bearish / neutral
    reasons: list[str] = field(default_factory=list)   # 依据（为什么这样建议）
    caveats: list[str] = field(default_factory=list)   # 风险提示
    # 加权明细：bias 由 factors 加总得出。不进 API schema，仅供测试与排查——
    # 结论和依据一旦对不上，看这两个字段就能定位是哪一项权重出了问题。
    score: float = 0.0
    factors: list[BiasFactor] = field(default_factory=list)


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
    # 大白话形态解读（趋势 / 位置 / 量价 / 动能），供普通用户理解当前市场在做什么
    narrative: MarketNarrative | None = None

    # 最右侧未确认结构的提示（把缠论的右侧滞后不确定性显式暴露出来）
    pending_notes: list[str] = field(default_factory=list)

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

    @property
    def has_pending_structure(self) -> bool:
        """最右侧是否存在未确认结构（笔/线段/中枢/信号任一未确认）"""
        return bool(self.pending_notes)


class ChanAnalyzer:
    """缠论分析器"""

    def analyze(
        self, symbol: str, bars: list[dict], *, min_gap: int = 4, lang: str = "zh"
    ) -> ChanAnalysisResult:
        """对K线数据执行完整缠论分析。

        bars: list of {time, open, high, low, close, volume}
        min_gap: 笔成立所需的最小分型间隔（合并K线数 - 1），默认 4（缠论新笔标准）
        lang: 输出文案语言（zh / en）
        """
        logger.info("chan_analysis_start", symbol=symbol, bars=len(bars), min_gap=min_gap)

        result = ChanAnalysisResult(symbol=symbol, bars_count=len(bars))

        if len(bars) < 10:
            result.summary = pick(lang, "K线数据不足（最少需要10根），无法进行缠论分析",
                                  "Not enough candles (at least 10 required) for Chan analysis")
            return result

        # 1. 包含关系处理
        result.merged_candles = merge_candles(bars)
        logger.debug("chan_merged_candles", count=len(result.merged_candles))

        # 2. 分型识别
        result.fractals = find_fractals(result.merged_candles)
        logger.debug("chan_fractals", count=len(result.fractals))

        if len(result.fractals) < 2:
            result.summary = pick(
                lang,
                f"分型不足（仅{len(result.fractals)}个），行情可能处于单边走势",
                f"Too few fractals (only {len(result.fractals)}); the market may be in a one-way move",
            )
            return result

        # 3. 笔识别
        result.strokes = find_strokes(result.fractals, min_gap=min_gap)
        logger.debug("chan_strokes", count=len(result.strokes))

        if len(result.strokes) < 3:
            result.summary = pick(
                lang,
                f"笔数量不足（仅{len(result.strokes)}笔），无法识别线段和中枢",
                f"Too few strokes (only {len(result.strokes)}) to identify segments and pivots",
            )
            result.current_trend = self._infer_trend_from_strokes(result.strokes, lang)
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
        result.divergences = find_stroke_divergences(result.strokes, result.macd, lang)
        diverged_count = sum(1 for d in result.divergences if d.is_diverged)
        logger.debug("chan_divergences", total=len(result.divergences), diverged=diverged_count)

        # 8. 买卖点生成（使用笔级别中枢）
        all_pivots = result.stroke_pivots + result.segment_pivots
        all_pivots.sort(key=lambda p: p.start_time)
        result.signals = generate_all_signals(result.strokes, result.divergences, all_pivots, lang)
        logger.debug("chan_signals", count=len(result.signals))

        # 9. 标注最右侧未确认结构（右侧滞后不确定性）
        self._mark_confirmations(result)
        result.pending_notes = self._build_pending_notes(result, lang)

        # 10. 当前状态摘要
        result.current_trend = self._infer_trend_from_strokes(result.strokes, lang)
        result.latest_signal = result.signals[-1] if result.signals else None
        result.summary = self._build_summary(result, lang)
        # 量价需要原始 bars（合并K线不含 volume），故两处都在此传入
        result.recommendation = self._build_recommendation(result, bars, lang)
        result.narrative = build_narrative(result, bars, lang)

        logger.info(
            "chan_analysis_complete",
            symbol=symbol,
            strokes=len(result.strokes),
            pivots=len(result.stroke_pivots),
            signals=len(result.signals),
        )
        return result

    def _infer_trend_from_strokes(self, strokes: list[Stroke], lang: str = "zh") -> str:
        if not strokes:
            return pick(lang, "数据不足", "Not enough data")
        last = strokes[-1]
        if last.direction == "up":
            return pick(lang, "当前处于上升笔末端", "At the end of a rising leg (up-leg)")
        return pick(lang, "当前处于下降笔末端", "At the end of a falling leg (down-leg)")

    def _mark_confirmations(self, r: ChanAnalysisResult) -> None:
        """标注各层结构是否已确认。

        缠论的结构在其“完成”那一刻才在图上成立，而最右侧的结构永远处于
        “等待后续K线确认”的状态——分型可能随包含处理移动/消失，笔的端点可能被
        突破延伸，线段结束需特征序列确认，中枢可能仍在延伸。这里把这种右侧
        不确定性显式标注出来，避免把几何结构误当作确定性。
        """
        # 分型：右侧K线必须不是最后一根合并K线，形态才算锁定
        last_mc_idx = len(r.merged_candles) - 1
        for f in r.fractals:
            # f.idx 为分型中心K线索引，右侧K线索引 = f.idx + 1
            f.confirmed = (f.idx + 1) < last_mc_idx

        # 统一原则：一个结构只要仍触及“构成它的下层序列”的最右端
        # （尚无后续下层元素离开/翻转来锁定它），就算未确认。

        # 笔：最后一笔处于右侧前沿（端点可能延伸/反转），未确认；
        #     端点分型形态未锁定的笔亦未确认。
        for i, s in enumerate(r.strokes):
            is_last = i == len(r.strokes) - 1
            s.confirmed = (not is_last) and s.end.confirmed

        # 线段：由笔构成，仅当仍含整段笔序列的最末一笔时未确认
        # （此时尚无后续笔离开以锁定其结束；一旦有笔离开，线段即已确认，
        #  即便它是最后一条线段）。
        last_stroke = r.strokes[-1] if r.strokes else None
        for seg in r.segments:
            still_frontier = (
                last_stroke is not None and bool(seg.strokes) and seg.strokes[-1] is last_stroke
            )
            seg.confirmed = not still_frontier

        # 中枢：由笔/线段构成，仅当仍含整段序列的最末元素时未确认。
        for pivots, elements in ((r.stroke_pivots, r.strokes), (r.segment_pivots, r.segments)):
            last_elem = elements[-1] if elements else None
            for p in pivots:
                still_frontier = (
                    last_elem is not None and bool(p.elements) and p.elements[-1] is last_elem
                )
                p.confirmed = not still_frontier

        # 信号：落在未确认笔（端点时间）之上的信号未确认
        unconfirmed_end_times = {s.end_time for s in r.strokes if not s.confirmed}
        for sig in r.signals:
            sig.confirmed = sig.time not in unconfirmed_end_times

    def _build_pending_notes(self, r: ChanAnalysisResult, lang: str = "zh") -> list[str]:
        """汇总最右侧未确认结构，生成人类可读的提示。"""
        notes: list[str] = []
        en = is_en(lang)

        if r.fractals and not r.fractals[-1].confirmed:
            f = r.fractals[-1]
            if en:
                kind = "top fractal" if f.type == "top" else "bottom fractal"
                notes.append(
                    f"The latest {kind} ({f.time}, {f.price:.2f}) is not yet confirmed by later "
                    f"candles and may move or disappear"
                )
            else:
                kind = "顶分型" if f.type == "top" else "底分型"
                notes.append(
                    f"最新{kind}（{f.time}，{f.price:.2f}）尚未被后续K线确认，"
                    f"新K线可能使其移动或消失"
                )

        if r.strokes and not r.strokes[-1].confirmed:
            s = r.strokes[-1]
            if en:
                dir_name = "rising" if s.direction == "up" else "falling"
                notes.append(
                    f"The last stroke ({dir_name}, since {s.start_time}) is unfinished; its endpoint "
                    f"{s.end_price:.2f} may be broken and extended by later candles"
                )
            else:
                dir_name = "上升" if s.direction == "up" else "下降"
                notes.append(
                    f"最后一笔（{dir_name}笔，起于 {s.start_time}）尚未完成，"
                    f"端点 {s.end_price:.2f} 可能被后续K线突破而延伸"
                )

        if r.segments and not r.segments[-1].confirmed:
            seg = r.segments[-1]
            if en:
                dir_name = "rising" if seg.direction == "up" else "falling"
                notes.append(
                    f"The last segment ({dir_name}, since {seg.start_time}) hasn't confirmed its end; "
                    f"direction may still swing"
                )
            else:
                dir_name = "上升" if seg.direction == "up" else "下降"
                notes.append(
                    f"最后一条线段（{dir_name}，起于 {seg.start_time}）尚未确认结束，"
                    f"方向可能反复"
                )

        pivot_names = (
            (r.stroke_pivots, pick(lang, "笔级中枢", "stroke-level pivot")),
            (r.segment_pivots, pick(lang, "线段级中枢", "segment-level pivot")),
        )
        for pivots, name in pivot_names:
            if pivots and not pivots[-1].confirmed:
                p = pivots[-1]
                if en:
                    notes.append(
                        f"The latest {name} ({p.zd:.2f}–{p.zg:.2f}) may still be extending; its bounds "
                        f"and exit direction aren't finalized"
                    )
                else:
                    notes.append(
                        f"最近{name}（{p.zd:.2f}–{p.zg:.2f}）可能仍在延伸，"
                        f"上下沿与离开方向尚未最终确认"
                    )

        pending_signals = [s for s in r.signals if not s.confirmed]
        if pending_signals:
            if en:
                labels = ", ".join(dict.fromkeys(s.label for s in pending_signals))
                notes.append(
                    f"The latest {labels} signal(s) sit on an unconfirmed stroke — a left-side "
                    f"anticipation that needs later candles to verify; don't size up on it"
                )
            else:
                labels = "、".join(dict.fromkeys(s.label for s in pending_signals))
                notes.append(
                    f"最新的 {labels} 信号位于未确认笔上，属于左侧预判，"
                    f"需后续K线验证，切勿据此重仓"
                )

        return notes

    def _build_recommendation(
        self, r: ChanAnalysisResult, bars: list[dict] | None = None, lang: str = "zh"
    ) -> Recommendation:
        """综合缠论各维度加权，描述当前技术形态倾向及依据（不构成操作建议）。

        每个维度（最近信号 / 末笔 / 线段 / 中枢位置 / 背驰 / 量价）折算成一个带符号
        的分数，加总后才定多空。改造前 bias 只由「末笔方向 × 背驰」单独决定，
        结论会和自己列出的依据打架——顶背驰时判「偏空」，可下面挂着「多头占优、
        大级别趋势偏多」。现在背驰只是一个扣分项，不再单独掀翻方向。

        措辞只描述技术形态，不含操作动词。
        """
        caveats: list[str] = []
        en = is_en(lang)
        factors: list[BiasFactor] = []

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
        # 趋势方向从最后一笔取，避免解析已本地化的 current_trend 文本
        last_dir = r.strokes[-1].direction if r.strokes else None

        # ---- 因子 1：最近的买卖点信号 ----
        if signal_fresh and latest is not None:
            weight = SIGNAL_WEIGHT[latest.strength]
            if not latest.confirmed:
                weight *= UNCONFIRMED_DISCOUNT
            if en:
                tag = "" if latest.confirmed else " (on an unconfirmed stroke, a left-side call)"
                text = (f"Recent {latest.label} ({latest.strength} strength, {latest.time}){tag}: "
                        f"{latest.description}")
            else:
                tag = "" if latest.confirmed else "（该信号所在笔未确认，为左侧预判）"
                strength_cn = {"strong": "强", "medium": "中", "weak": "弱"}[latest.strength]
                text = (f"最近出现{latest.label}（{strength_cn}强度，{latest.time}）{tag}："
                        f"{latest.description}")
            factors.append(BiasFactor(text, weight if latest.is_buy else -weight))

        # ---- 因子 2：末笔方向（短期节奏）----
        if last_dir == "up":
            factors.append(BiasFactor(pick(lang,
                "当前处于上升笔末端，短期节奏向上",
                "At the end of a rising leg — the short-term rhythm points up"), STROKE_WEIGHT))
        elif last_dir == "down":
            factors.append(BiasFactor(pick(lang,
                "当前处于下降笔末端，短期节奏向下",
                "At the end of a falling leg — the short-term rhythm points down"), -STROKE_WEIGHT))

        # ---- 因子 3：线段方向（大级别趋势，权重高于笔）----
        if r.segments:
            up = r.segments[-1].direction == "up"
            if en:
                text = (f"The latest segment points {'up' if up else 'down'}, so the larger-degree "
                        f"trend leans {'bullish' if up else 'bearish'}")
            else:
                text = (f"最近线段方向{'向上' if up else '向下'}，"
                        f"大级别趋势{'偏多' if up else '偏空'}")
            factors.append(BiasFactor(text, SEGMENT_WEIGHT if up else -SEGMENT_WEIGHT))

        # ---- 因子 4：当前价相对最近中枢的位置 ----
        if r.stroke_pivots:
            p = r.stroke_pivots[-1]
            if last_price > p.zg:
                factors.append(BiasFactor(pick(lang,
                    f"当前价 {last_price:.2f} 站上最近中枢上沿 ZG（{p.zg:.2f}），多头占优",
                    f"Price {last_price:.2f} is above the latest pivot's upper bound ZG ({p.zg:.2f}); "
                    f"bulls have the edge"), PIVOT_WEIGHT))
            elif last_price < p.zd:
                factors.append(BiasFactor(pick(lang,
                    f"当前价 {last_price:.2f} 跌破最近中枢下沿 ZD（{p.zd:.2f}），空头占优",
                    f"Price {last_price:.2f} is below the latest pivot's lower bound ZD ({p.zd:.2f}); "
                    f"bears have the edge"), -PIVOT_WEIGHT))
            else:
                factors.append(BiasFactor(pick(lang,
                    f"当前价 {last_price:.2f} 仍在最近中枢（{p.zd:.2f}–{p.zg:.2f}）内，多空交战、方向待选",
                    f"Price {last_price:.2f} is still inside the latest pivot ({p.zd:.2f}–{p.zg:.2f}); "
                    f"a stand-off with direction undecided"), 0.0))

        # ---- 因子 5：背驰（只削弱当前方向的力度）----
        if recent_div_dir == "up":
            factors.append(BiasFactor(pick(lang,
                "上涨过程中出现顶背驰：价格创新高但动能没跟上，上涨力度在衰减",
                "A top divergence appeared during the advance: price made new highs but momentum "
                "didn't follow — the push is decaying"), -DIVERGENCE_WEIGHT))
        elif recent_div_dir == "down":
            factors.append(BiasFactor(pick(lang,
                "下跌过程中出现底背驰：价格创新低但动能在减弱，下跌力度在衰减",
                "A bottom divergence appeared during the decline: price made new lows but momentum "
                "weakened — the selling is decaying"), DIVERGENCE_WEIGHT))

        # ---- 因子 6：量价配合 ----
        if bars:
            vol = _volume_readout(bars, lang)
            if vol:
                factors.append(BiasFactor(vol[1], vol[2]))

        # ---- 加权定调 ----
        score = sum(f.score for f in factors)
        bias = score_to_bias(score)
        label = self._bias_label(score, bias, recent_div_dir, lang)

        if signal_fresh and latest is not None and latest.is_buy == (bias == "bullish"):
            action = "buy" if latest.is_buy else "sell"
        elif bias == "bullish":
            action = "hold_bullish"
        elif bias == "bearish":
            action = "hold_bearish"
        else:
            action = "watch"

        # 汇总句打头：先说清结论是加权净值，下面单条依据与结论反向才不像自相矛盾
        reasons = [self._factor_summary(factors, lang)] + [f.text for f in factors]
        if not factors:
            reasons.append(pick(lang, "当前走势结构尚不明确，方向有待后续K线确认",
                                "The structure isn't clear yet; direction awaits later candles"))

        # 把最右侧未确认结构作为具体风险提示暴露出来
        caveats.extend(r.pending_notes)
        caveats.append(pick(lang,
            "缠论分型 / 笔需后续K线确认，信号存在滞后性",
            "Chan fractals/strokes need later candles to confirm; signals are inherently lagging"))
        caveats.append(pick(lang,
            "以上均为缠论技术形态的客观描述，不构成任何投资建议；"
            "技术上的“买点”不等于投资上“值得买”，请结合基本面、估值与风险自主决策",
            "All of the above objectively describes Chan technical structure and is not investment "
            "advice; a technical \"buy point\" is not the same as being \"worth buying\" — decide for "
            "yourself, weighing fundamentals, valuation and risk"))

        return Recommendation(action=action, action_label=label, bias=bias, reasons=reasons,
                              caveats=caveats, score=score, factors=factors)

    def _bias_label(
        self, score: float, bias: str, div_dir: str | None, lang: str = "zh"
    ) -> str:
        """把加权分数说成人话：强弱程度 + 动能是否在衰减。

        动能衰减降级为后缀而不是主语——它描述的是力度的二阶变化（还在涨、只是
        变慢），跟「多空方向」不是一回事，写成主语就会和 chip 上的倾向打架。
        """
        strong = abs(score) >= STRONG_BIAS_THRESHOLD
        if bias == "bullish":
            label = pick(lang, "技术面偏强" if strong else "技术面略偏强",
                         "Technicals firm" if strong else "Technicals mildly firm")
        elif bias == "bearish":
            label = pick(lang, "技术面偏弱" if strong else "技术面略偏弱",
                         "Technicals soft" if strong else "Technicals mildly soft")
        else:
            label = pick(lang, "技术面多空僵持", "Technicals balanced")

        if div_dir == "up":
            label += pick(lang, "，上涨动能转弱", ", upside momentum fading")
        elif div_dir == "down":
            label += pick(lang, "，下跌动能转弱", ", downside momentum fading")
        return label

    def _factor_summary(self, factors: list[BiasFactor], lang: str = "zh") -> str:
        """依据列表的开场白：说明结论是这些因子的加权净值。

        没有这一句，用户看到「偏多」下面挂着一条「空头占优」，只会觉得是 bug。
        """
        bull = sum(1 for f in factors if f.score > 0)
        bear = sum(1 for f in factors if f.score < 0)
        flat = len(factors) - bull - bear
        if is_en(lang):
            return (f"Weighing {len(factors)} technical factors: {bull} bullish, {bear} bearish, "
                    f"{flat} neutral. The bias above is their weighted net, so individual lines "
                    f"below may point the other way")
        return (f"综合 {len(factors)} 项技术因子加权：{bull} 项偏多、{bear} 项偏空、{flat} 项中性。"
                f"上方倾向是加权净值，故下列单条依据可能与结论方向相反")

    def _build_summary(self, r: ChanAnalysisResult, lang: str = "zh") -> str:
        en = is_en(lang)
        buy_signals = [s for s in r.signals if s.is_buy]
        sell_signals = [s for s in r.signals if not s.is_buy]

        if en:
            parts = [
                f"Identified {len(r.merged_candles)} merged candles, {len(r.fractals)} fractals, "
                f"{len(r.strokes)} strokes, {len(r.segments)} segments, "
                f"{len(r.stroke_pivots)} stroke-level pivots, "
                f"{len(r.segment_pivots)} segment-level pivots. "
            ]
            if r.current_trend:
                parts.append(r.current_trend + ". ")
            if r.signals:
                parts.append(
                    f"Found {len(buy_signals)} buy signal(s) and {len(sell_signals)} sell signal(s). ")
            if r.latest_signal:
                s = r.latest_signal
                tag = "" if s.confirmed else " (unconfirmed, needs later candles)"
                parts.append(
                    f"Latest signal: {s.label} ({s.strength} strength), time={s.time}, "
                    f"price={s.price:.2f}{tag}. ")
            if r.pending_notes:
                parts.append("[Unconfirmed at the right edge] " + "; ".join(r.pending_notes) + ".")
            return "".join(parts)

        parts = [
            f"共识别 {len(r.merged_candles)} 根合并K线，"
            f"{len(r.fractals)} 个分型，{len(r.strokes)} 笔，"
            f"{len(r.segments)} 条线段，"
            f"{len(r.stroke_pivots)} 个笔级中枢，"
            f"{len(r.segment_pivots)} 个线段级中枢。",
        ]
        if r.current_trend:
            parts.append(r.current_trend + "。")
        if r.signals:
            parts.append(
                f"共发现 {len(buy_signals)} 个买点信号、{len(sell_signals)} 个卖点信号。"
            )
        if r.latest_signal:
            s = r.latest_signal
            parts.append(
                f"最近信号：{s.label}（{s.strength}强度），时间={s.time}，价格={s.price:.2f}"
                f"{'' if s.confirmed else '（未确认，需后续K线验证）'}。"
            )
        if r.pending_notes:
            parts.append("【最右侧未确认】" + "；".join(r.pending_notes) + "。")
        return "".join(parts)
