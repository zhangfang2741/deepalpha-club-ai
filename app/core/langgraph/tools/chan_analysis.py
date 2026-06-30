"""缠论分析 LangGraph 工具：让 AI Agent 能够用缠论分析股票"""
from __future__ import annotations


from app.core.logging import logger
from app.services.chan.analyzer import ChanAnalyzer
from app.services.skills.kline import fetch_kline

_analyzer = ChanAnalyzer()


async def chan_analysis_tool(
    symbol: str,
    start_date: str,
    end_date: str,
    freq: str = "daily",
) -> str:
    """使用缠论（缠中说禅理论）对股票进行技术分析。

    分析内容：
    - 识别分型（顶底分型），过滤K线包含关系
    - 识别笔（相邻顶底分型间的价格走势）
    - 识别线段（至少3笔构成的趋势结构）
    - 识别中枢（价格震荡区域 ZG/ZD）
    - 判断背驰（MACD面积背驰，识别趋势转折）
    - 生成三类买卖点（一买/二买/三买及对应卖点）

    返回详细的文本分析报告，供用户参考投资决策。
    """
    logger.info("chan_tool_called", symbol=symbol, start=start_date, end=end_date)

    bars = await fetch_kline(
        user_id=None,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        freq=freq,
    )

    if not bars:
        return f"未能获取 {symbol} 的K线数据，请检查股票代码和日期范围。"

    result = _analyzer.analyze(symbol, bars)

    lines = [
        f"## {symbol} 缠论分析报告",
        f"**分析周期**：{start_date} → {end_date}（{freq}）",
        f"**K线数量**：原始 {len(bars)} 根，合并后 {len(result.merged_candles)} 根",
        "",
        "### 结构识别",
        f"- 分型：{len(result.fractals)} 个（顶分型 {sum(1 for f in result.fractals if f.type == 'top')} / 底分型 {sum(1 for f in result.fractals if f.type == 'bottom')}）",
        f"- 笔：{len(result.strokes)} 笔（上升 {sum(1 for s in result.strokes if s.direction == 'up')} / 下降 {sum(1 for s in result.strokes if s.direction == 'down')}）",
        f"- 线段：{len(result.segments)} 条",
        f"- 中枢（笔级别）：{len(result.stroke_pivots)} 个",
        f"- 中枢（线段级别）：{len(result.segment_pivots)} 个",
        "",
    ]

    if result.stroke_pivots:
        lines.append("### 近期中枢")
        for p in result.stroke_pivots[-3:]:
            lines.append(
                f"- {p.start_time} ~ {p.end_time}：ZD={p.zd:.2f} / ZG={p.zg:.2f}"
                f"（区间宽度 {p.height:.2f}，{p.level}级别）"
            )
        lines.append("")

    if result.signals:
        lines.append("### 买卖点信号（按时间）")
        for sig in result.signals[-10:]:
            strength_emoji = {"strong": "🔥", "medium": "⚡", "weak": "💡"}.get(sig.strength, "")
            lines.append(
                f"- **{sig.label}** {strength_emoji} | {sig.time} | 价格={sig.price:.2f} | {sig.description[:80]}"
            )
        lines.append("")

    diverged = [d for d in result.divergences if d.is_diverged]
    if diverged:
        latest_div = diverged[-1]
        lines.append("### 最近背驰信号")
        lines.append(f"- {latest_div.description}")
        lines.append("")

    lines.append("### 当前状态")
    lines.append(result.summary or "暂无总结")

    if result.latest_signal:
        s = result.latest_signal
        lines.append(f"\n**最新信号**：{s.label}（{s.strength}强度），{s.time}，价格 {s.price:.2f}")
        lines.append(f"> {s.description}")

    return "\n".join(lines)
