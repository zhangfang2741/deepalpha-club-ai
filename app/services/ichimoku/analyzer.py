"""一目均衡表分析主协调器：计算五线 → 平移组装 → 状态判读 → 操作建议。

一目均衡表（Ichimoku Kinko Hyo）五要素：
  转换线 Tenkan、基准线 Kijun、先行带 A/B（前移 26 根构成「云 Kumo」）、迟行线 Chikou。
判读核心「三役」：价格相对云、转换线相对基准线、迟行线相对价格，三者同向即强信号。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.core.logging import logger
from app.services.ichimoku.indicators import (
    LinePoint,
    base_line,
    conversion_line,
    leading_span_a,
    leading_span_b,
)
from app.services.ichimoku.signals import IchimokuSignal, generate_signals


@dataclass
class CandleOut:
    time: str
    open: float
    high: float
    low: float
    close: float


@dataclass
class IchimokuState:
    """当前（最新一根 K 线）的一目均衡表状态。"""

    price: float
    price_vs_cloud: str      # above / in / below / na
    cloud_color: str         # bullish（阳云）/ bearish（阴云）/ na
    tk_relation: str         # tenkan_above / tenkan_below / aligned / na
    chikou_relation: str     # above / below / na
    tenkan: float | None = None
    kijun: float | None = None
    cloud_top: float | None = None
    cloud_bottom: float | None = None


@dataclass
class Recommendation:
    """综合三役给出的操作建议。"""

    action: str          # buy / sell / hold_bullish / hold_bearish / watch
    action_label: str    # 中文操作标签
    bias: str            # bullish / bearish / neutral
    reasons: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)


@dataclass
class IchimokuAnalysisResult:
    """一目均衡表完整分析结果。"""

    symbol: str
    bars_count: int

    candles: list[CandleOut] = field(default_factory=list)
    tenkan: list[LinePoint] = field(default_factory=list)
    kijun: list[LinePoint] = field(default_factory=list)
    senkou_a: list[LinePoint] = field(default_factory=list)   # 已前移
    senkou_b: list[LinePoint] = field(default_factory=list)   # 已前移
    chikou: list[LinePoint] = field(default_factory=list)     # 已后移
    signals: list[IchimokuSignal] = field(default_factory=list)

    state: IchimokuState | None = None
    summary: str = ""
    recommendation: Recommendation | None = None

    @property
    def latest_signal(self) -> IchimokuSignal | None:
        return self.signals[-1] if self.signals else None


class IchimokuAnalyzer:
    """一目均衡表分析器。"""

    def __init__(
        self,
        conversion_period: int = 9,
        base_period: int = 26,
        span_b_period: int = 52,
        displacement: int = 26,
    ) -> None:
        self.conversion_period = conversion_period
        self.base_period = base_period
        self.span_b_period = span_b_period
        self.displacement = displacement

    def analyze(self, symbol: str, bars: list[dict]) -> IchimokuAnalysisResult:
        """对 K 线执行完整一目均衡表分析。

        bars: list of {time, open, high, low, close, volume}
        """
        logger.info("ichimoku_analysis_start", symbol=symbol, bars=len(bars))

        result = IchimokuAnalysisResult(symbol=symbol, bars_count=len(bars))
        result.candles = [
            CandleOut(
                time=str(b["time"]),
                open=float(b["open"]),
                high=float(b["high"]),
                low=float(b["low"]),
                close=float(b["close"]),
            )
            for b in bars
        ]

        # 至少需要「先行带 B 周期 + 平移」根才能构成完整的云
        if len(bars) < self.base_period + 1:
            result.summary = (
                f"K 线数据不足（仅 {len(bars)} 根，至少需 {self.base_period + 1} 根），"
                "无法计算一目均衡表基准线"
            )
            return result

        conv = conversion_line(bars, self.conversion_period)
        base = base_line(bars, self.base_period)
        span_a_raw = leading_span_a(conv, base)
        span_b_raw = leading_span_b(bars, self.span_b_period)

        times = [str(b["time"]) for b in bars]
        future_times = self._future_times(times, self.displacement)

        # ── 转换线 / 基准线：与 K 线同时间轴 ──────────────────────────
        result.tenkan = _to_points(times, conv)
        result.kijun = _to_points(times, base)

        # ── 先行带 A/B：向前（未来）平移 displacement 根 ──────────────
        result.senkou_a = self._shift_forward(times, future_times, span_a_raw)
        result.senkou_b = self._shift_forward(times, future_times, span_b_raw)

        # ── 迟行线：当期收盘价向后（过去）平移 displacement 根 ────────
        result.chikou = self._chikou(bars, self.displacement)

        # ── 买卖信号 ─────────────────────────────────────────────
        result.signals = generate_signals(
            bars, conv, base, span_a_raw, span_b_raw, self.displacement
        )
        logger.debug("ichimoku_signals", count=len(result.signals))

        # ── 当前状态 + 建议 + 摘要 ────────────────────────────────
        result.state = self._current_state(bars, conv, base, span_a_raw, span_b_raw)
        result.recommendation = self._build_recommendation(result.state)
        result.summary = self._build_summary(result)

        logger.info(
            "ichimoku_analysis_complete",
            symbol=symbol,
            signals=len(result.signals),
            price_vs_cloud=result.state.price_vs_cloud if result.state else "na",
        )
        return result

    # ── 时间轴平移 ────────────────────────────────────────────────
    def _shift_forward(
        self, times: list[str], future_times: list[str], values: list[float | None]
    ) -> list[LinePoint]:
        """把按 bar 下标算得的先行带前移 displacement 根显示。"""
        d = self.displacement
        axis = times + future_times  # 长度 = N + displacement
        points: list[LinePoint] = []
        for i, v in enumerate(values):
            if v is None:
                continue
            j = i + d
            if j < len(axis):
                points.append(LinePoint(time=axis[j], value=v))
        return points

    def _chikou(self, bars: list[dict], displacement: int) -> list[LinePoint]:
        """迟行线：close[j+displacement] 画在 time[j]（当期收盘后移）。"""
        points: list[LinePoint] = []
        for j in range(len(bars) - displacement):
            points.append(
                LinePoint(time=str(bars[j]["time"]), value=float(bars[j + displacement]["close"]))
            )
        return points

    def _future_times(self, times: list[str], count: int) -> list[str]:
        """在末尾生成 count 个未来时间标签。

        依据历史相邻 bar 的中位间隔推断步长（日线≈1、周线≈7），
        步长 ≤3 天视为日线，跳过周末；否则按固定步长外推。
        """
        if not times:
            return []
        parsed = [_parse_date(t) for t in times]
        deltas = sorted(
            (parsed[i] - parsed[i - 1]).days
            for i in range(1, len(parsed))
            if (parsed[i] - parsed[i - 1]).days > 0
        )
        step = deltas[len(deltas) // 2] if deltas else 1
        daily = step <= 3

        out: list[str] = []
        cur = parsed[-1]
        while len(out) < count:
            cur = cur + timedelta(days=1 if daily else step)
            if daily and cur.weekday() >= 5:  # 跳过周六日
                continue
            out.append(cur.isoformat())
        return out

    # ── 当前状态判读 ──────────────────────────────────────────────
    def _current_state(
        self,
        bars: list[dict],
        conv: list[float | None],
        base: list[float | None],
        span_a_raw: list[float | None],
        span_b_raw: list[float | None],
    ) -> IchimokuState:
        n = len(bars)
        i = n - 1
        close = float(bars[i]["close"])
        d = self.displacement

        # 当前显示的云由 i-d 处算得
        src = i - d
        cloud_top = cloud_bottom = None
        cloud_color = "na"
        price_vs_cloud = "na"
        if src >= 0 and span_a_raw[src] is not None and span_b_raw[src] is not None:
            a, b = span_a_raw[src], span_b_raw[src]
            cloud_top, cloud_bottom = max(a, b), min(a, b)
            cloud_color = "bullish" if a >= b else "bearish"
            if close > cloud_top:
                price_vs_cloud = "above"
            elif close < cloud_bottom:
                price_vs_cloud = "below"
            else:
                price_vs_cloud = "in"

        tenkan, kijun = conv[i], base[i]
        if tenkan is None or kijun is None:
            tk_relation = "na"
        elif tenkan > kijun:
            tk_relation = "tenkan_above"
        elif tenkan < kijun:
            tk_relation = "tenkan_below"
        else:
            tk_relation = "aligned"

        # 迟行线：当期收盘 vs displacement 根前的收盘
        chikou_relation = "na"
        if i - d >= 0:
            past_close = float(bars[i - d]["close"])
            chikou_relation = "above" if close > past_close else "below" if close < past_close else "aligned"

        return IchimokuState(
            price=close,
            price_vs_cloud=price_vs_cloud,
            cloud_color=cloud_color,
            tk_relation=tk_relation,
            chikou_relation=chikou_relation,
            tenkan=tenkan,
            kijun=kijun,
            cloud_top=cloud_top,
            cloud_bottom=cloud_bottom,
        )

    def _build_recommendation(self, state: IchimokuState) -> Recommendation:
        """三役好转 / 逆转判读。

        三役看多：价格在云上 + 转换线在基准线上 + 迟行线在价格上；
        三役看空则相反。计多空票数给出建议。
        """
        reasons: list[str] = []
        caveats: list[str] = []

        bull = 0
        bear = 0

        if state.price_vs_cloud == "above":
            bull += 1
            reasons.append(f"价格站上云层上沿（{_fmt(state.cloud_top)}），趋势偏多")
        elif state.price_vs_cloud == "below":
            bear += 1
            reasons.append(f"价格跌破云层下沿（{_fmt(state.cloud_bottom)}），趋势偏空")
        else:
            reasons.append("价格位于云层之中，多空交战、方向待选")

        if state.tk_relation == "tenkan_above":
            bull += 1
            reasons.append(f"转换线（{_fmt(state.tenkan)}）在基准线（{_fmt(state.kijun)}）之上，短期动能偏多")
        elif state.tk_relation == "tenkan_below":
            bear += 1
            reasons.append(f"转换线（{_fmt(state.tenkan)}）在基准线（{_fmt(state.kijun)}）之下，短期动能偏空")

        if state.chikou_relation == "above":
            bull += 1
            reasons.append("迟行线位于价格之上，回看动能确认多头")
        elif state.chikou_relation == "below":
            bear += 1
            reasons.append("迟行线位于价格之下，回看动能确认空头")

        if state.cloud_color == "bullish":
            reasons.append("前方云为阳云（先行带 A 在 B 之上），未来支撑偏强")
        elif state.cloud_color == "bearish":
            reasons.append("前方云为阴云（先行带 A 在 B 之下），未来压制偏强")

        if bull == 3:
            action, label, bias = "buy", "三役好转，多头强势，可关注买入", "bullish"
        elif bear == 3:
            action, label, bias = "sell", "三役逆转，空头强势，可关注卖出/减仓", "bearish"
        elif bull >= 2 and bull > bear:
            action, label, bias = "hold_bullish", "多方占优，偏多持有", "bullish"
        elif bear >= 2 and bear > bull:
            action, label, bias = "hold_bearish", "空方占优，偏空谨慎", "bearish"
        else:
            action, label, bias = "watch", "多空不明，建议观望", "neutral"

        caveats.append("一目均衡表以中值构建，横盘时转换/基准线易频繁交叉，信号可靠性下降")
        caveats.append("先行带前移 26 期为未来预判，属推演而非确定，请结合实际走势验证")
        caveats.append("本建议为技术面参考，不构成投资建议，请结合基本面与风险自行决策")

        return Recommendation(action=action, action_label=label, bias=bias, reasons=reasons, caveats=caveats)

    def _build_summary(self, r: IchimokuAnalysisResult) -> str:
        s = r.state
        if s is None:
            return r.summary
        parts = [
            f"共分析 {r.bars_count} 根 K 线，识别 {len(r.signals)} 个买卖信号。",
        ]
        pos_cn = {"above": "云层上方", "below": "云层下方", "in": "云层之中", "na": "云外/数据不足"}
        color_cn = {"bullish": "阳云（看涨）", "bearish": "阴云（看跌）", "na": "未定"}
        parts.append(
            f"当前价 {_fmt(s.price)} 位于{pos_cn.get(s.price_vs_cloud, '')}，"
            f"前方为{color_cn.get(s.cloud_color, '')}。"
        )
        if s.tk_relation == "tenkan_above":
            parts.append("转换线在基准线之上（短期偏多）。")
        elif s.tk_relation == "tenkan_below":
            parts.append("转换线在基准线之下（短期偏空）。")
        if r.latest_signal:
            sig = r.latest_signal
            parts.append(f"最近信号：{sig.label}（{sig.strength}强度），时间={sig.time}，价格={_fmt(sig.price)}。")
        return "".join(parts)


def _to_points(times: list[str], values: list[float | None]) -> list[LinePoint]:
    return [LinePoint(time=t, value=v) for t, v in zip(times, values, strict=True) if v is not None]


def _parse_date(s: str) -> date:
    """解析日期字符串（取前 10 位 YYYY-MM-DD）。"""
    return date.fromisoformat(s[:10])


def _fmt(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else "N/A"
