"""威科夫分析主协调器：整合摆动点 → 交易区间 → 事件 → 阶段 → 三大定律 → 操作建议。"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logging import logger
from app.services.wyckoff.indicators import (
    VolumeStats,
    find_swings,
    volume_stats,
)
from app.services.wyckoff.laws import LawResult, analyze_laws
from app.services.wyckoff.phases import (
    STAGE_ACCUMULATION,
    STAGE_DISTRIBUTION,
    STAGE_MARKDOWN,
    STAGE_MARKUP,
    PhaseResult,
    determine_phase,
    position_in_range,
)
from app.services.wyckoff.structure import (
    StructureResult,
    TradingRange,
    WyckoffEvent,
    detect_structure,
)


@dataclass
class Recommendation:
    """当前操作建议（综合阶段 / 事件 / 区间位置 / 三大定律）。"""

    action: str          # accumulate / buy / hold / reduce / avoid / watch
    action_label: str    # 中文操作标签
    bias: str            # bullish / bearish / neutral
    reasons: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)


@dataclass
class WyckoffAnalysisResult:
    symbol: str
    bars_count: int

    context: str = "undetermined"          # accumulation / distribution / undetermined
    trading_range: TradingRange | None = None
    events: list[WyckoffEvent] = field(default_factory=list)
    phase: PhaseResult | None = None
    laws: list[LawResult] = field(default_factory=list)

    stage_label: str = ""
    position_desc: str = ""
    summary: str = ""
    recommendation: Recommendation | None = None

    @property
    def latest_event(self) -> WyckoffEvent | None:
        """最近一个威科夫事件。"""
        return self.events[-1] if self.events else None


class WyckoffAnalyzer:
    """威科夫方法论分析器。"""

    def analyze(
        self,
        symbol: str,
        bars: list[dict],
        *,
        swing_window: int = 3,
        climax_vol_ratio: float = 1.6,
        trend_min: float = 0.12,
    ) -> WyckoffAnalysisResult:
        """对 K 线执行完整威科夫分析。

        bars: list of {time, open, high, low, close, volume}
        swing_window: 摆动点识别的左右窗口
        climax_vol_ratio: 判定量能高潮所需的最小放量倍数
        trend_min: 高潮前所需的最小趋势幅度（SC 前下跌 / BC 前上涨）
        """
        logger.info("wyckoff_analysis_start", symbol=symbol, bars=len(bars))
        result = WyckoffAnalysisResult(symbol=symbol, bars_count=len(bars))

        if len(bars) < 20:
            result.summary = "K 线数据不足（最少需要 20 根），无法进行威科夫分析"
            return result

        vstats = volume_stats(bars)
        swings = find_swings(bars, left=swing_window, right=swing_window)
        logger.debug("wyckoff_swings", count=len(swings))

        if len(swings) < 3:
            result.summary = f"摆动点不足（仅 {len(swings)} 个），行情可能处于单边走势"
            return result

        structure: StructureResult = detect_structure(
            bars, swings, vstats, climax_vol_ratio=climax_vol_ratio, trend_min=trend_min
        )
        result.context = structure.context
        result.trading_range = structure.trading_range
        result.events = structure.events

        last_price = float(bars[-1]["close"])
        result.phase = determine_phase(structure, last_price)
        result.stage_label = result.phase.stage_label
        result.position_desc = position_in_range(structure.trading_range, last_price)
        result.laws = analyze_laws(bars, vstats, structure.trading_range)

        result.summary = self._build_summary(result)
        result.recommendation = self._build_recommendation(result, vstats)

        logger.info(
            "wyckoff_analysis_complete",
            symbol=symbol,
            context=result.context,
            events=len(result.events),
            stage=result.phase.stage if result.phase else None,
        )
        return result

    def _build_summary(self, r: WyckoffAnalysisResult) -> str:
        if r.context == "undetermined" or r.trading_range is None:
            return "未识别到清晰的交易区间与量能高潮，当前结构不明，建议观望。"

        tr = r.trading_range
        parts = [
            f"识别到{'吸筹' if tr.kind == 'accumulation' else '派发'}型交易区间 "
            f"{tr.support:.2f}–{tr.resistance:.2f}，共标记 {len(r.events)} 个威科夫事件。",
        ]
        # 已突破/跌破区间时，说明结构已演变为拉升或下跌，避免与阶段标签矛盾
        if r.phase and r.phase.breakout == "up":
            parts.append("价格已向上突破区间上沿，进入拉升。")
        elif r.phase and r.phase.breakout == "down":
            parts.append("价格已向下跌破区间下沿，进入下跌。")
        if r.phase:
            parts.append(f"当前处于{r.phase.stage_label}，{r.phase.phase_label}。")
        if r.position_desc:
            parts.append(r.position_desc + "。")
        if r.latest_event:
            e = r.latest_event
            parts.append(f"最近事件：{e.name}（{e.code}），时间 {e.time}，价格 {e.price:.2f}。")
        return "".join(parts)

    def _build_recommendation(self, r: WyckoffAnalysisResult, vstats: VolumeStats) -> Recommendation:
        reasons: list[str] = []
        caveats: list[str] = [
            "威科夫事件需后续 K 线确认，识别存在滞后性",
            "本建议为技术面参考，不构成投资建议，请结合基本面与风险自行决策",
        ]

        if r.phase is None or r.context == "undetermined":
            return Recommendation(
                action="watch", action_label="结构不明，建议观望", bias="neutral",
                reasons=["未识别到清晰的吸筹/派发结构与量能高潮"], caveats=caveats,
            )

        stage = r.phase.stage
        latest = r.latest_event
        latest_code = latest.code if latest else ""

        if stage == STAGE_ACCUMULATION:
            if latest_code in ("SPRING", "TEST", "LPS", "SOS"):
                action, label, bias = "accumulate", "吸筹后段，可分批低吸", "bullish"
                reasons.append(f"吸筹区间内出现 {latest.name}（{latest_code}），主力吸筹接近尾声，风险回报较优")
            else:
                action, label, bias = "watch", "吸筹进行中，等待弹簧/强势信号", "neutral"
                reasons.append("处于吸筹区间震荡，尚待 Spring 或 SOS 确认，宜观察不宜追高")
        elif stage == STAGE_MARKUP:
            action, label, bias = "buy", "拉升启动，趋势偏多可持有/回踩买入", "bullish"
            reasons.append("价格已向上突破交易区间，进入拉升阶段，趋势向上")
        elif stage == STAGE_DISTRIBUTION:
            if latest_code in ("UT", "UTAD", "SOW", "LPSY"):
                action, label, bias = "reduce", "派发后段，建议减仓/离场", "bearish"
                reasons.append(f"派发区间内出现 {latest.name}（{latest_code}），供给主导，上行空间有限")
            else:
                action, label, bias = "watch", "派发进行中，谨慎观望", "bearish"
                reasons.append("处于派发区间震荡，警惕 UTAD 诱多与后续破位")
        elif stage == STAGE_MARKDOWN:
            action, label, bias = "avoid", "下跌趋势，规避/空仓", "bearish"
            reasons.append("价格已向下跌破交易区间，进入下跌阶段，趋势向下")
        else:
            action, label, bias = "watch", "结构不明，建议观望", "neutral"
            reasons.append("走势结构尚不明确，建议观望等待明确信号")

        if r.position_desc:
            reasons.append(r.position_desc)

        # 三大定律佐证
        for law in r.laws:
            reasons.append(f"{law.name}：{law.verdict}")

        return Recommendation(action=action, action_label=label, bias=bias, reasons=reasons, caveats=caveats)

    def to_text_report(self, r: WyckoffAnalysisResult) -> str:
        """将分析结果渲染为供 AI Agent 使用的文本报告。"""
        lines = [f"# {r.symbol} 威科夫方法论分析", "", r.summary, ""]

        if r.trading_range is not None:
            tr = r.trading_range
            lines += [
                f"## 交易区间（{'吸筹' if tr.kind == 'accumulation' else '派发'}）",
                f"- 支撑：{tr.support:.2f}",
                f"- 阻力：{tr.resistance:.2f}",
                f"- 区间：{tr.start_time} 至今",
                "",
            ]

        if r.events:
            lines.append("## 威科夫事件序列")
            for e in r.events:
                lines.append(
                    f"- [{e.phase}阶段] {e.name}（{e.code}）｜{e.time}｜价 {e.price:.2f}"
                    f"｜量比 {e.volume_ratio}｜{e.description}"
                )
            lines.append("")

        if r.laws:
            lines.append("## 三大定律")
            for law in r.laws:
                lines.append(f"- {law.name}：{law.verdict}（{law.detail}）")
            lines.append("")

        if r.recommendation is not None:
            rec = r.recommendation
            lines += [f"## 操作建议：{rec.action_label}（{rec.bias}）", "依据："]
            lines += [f"- {x}" for x in rec.reasons]
            lines.append("风险提示：")
            lines += [f"- {x}" for x in rec.caveats]

        return "\n".join(lines)
