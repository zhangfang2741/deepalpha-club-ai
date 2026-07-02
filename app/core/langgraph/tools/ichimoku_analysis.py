"""一目均衡表分析 LangGraph 工具：让 AI Agent 能用一目均衡表分析股票"""
from __future__ import annotations

from app.cache.client import current_redis
from app.core.logging import logger
from app.services.ichimoku.analyzer import IchimokuAnalyzer
from app.services.skills.kline import fetch_kline

_analyzer = IchimokuAnalyzer()

_POS_CN = {"above": "云层上方", "below": "云层下方", "in": "云层之中", "na": "云外/数据不足"}
_COLOR_CN = {"bullish": "阳云（看涨）", "bearish": "阴云（看跌）", "na": "未定"}


async def ichimoku_analysis_tool(
    symbol: str,
    start_date: str,
    end_date: str,
    freq: str = "daily",
) -> str:
    """使用一目均衡表（Ichimoku Kinko Hyo）对股票进行技术分析。

    分析内容：转换线/基准线 TK 交叉、价格相对云（Kumo）的位置、云的多空色、
    迟行线确认，以及「三役」综合判读，生成买卖信号与操作建议。

    返回详细的文本分析报告，供用户参考投资决策。
    """
    logger.info("ichimoku_tool_called", symbol=symbol, start=start_date, end=end_date)

    try:
        bars = await fetch_kline(
            user_id=None,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            freq=freq,
            redis=current_redis(),
        )
    except ValueError as e:
        return f"获取 {symbol} 数据失败：{e}"

    if not bars:
        return f"未能获取 {symbol} 的K线数据，请检查股票代码和日期范围。"

    result = _analyzer.analyze(symbol, bars)
    s = result.state

    lines = [
        f"## {symbol} 一目均衡表分析报告",
        f"**分析周期**：{start_date} → {end_date}（{freq}）",
        f"**参数**：转换线 {_analyzer.conversion_period} / 基准线 {_analyzer.base_period} / "
        f"先行带B {_analyzer.span_b_period} / 平移 {_analyzer.displacement}",
        f"**K线数量**：{len(bars)} 根",
        "",
    ]

    if s is not None:
        lines += [
            "### 当前状态",
            f"- 最新价：{s.price:.2f}",
            f"- 价格相对云：{_POS_CN.get(s.price_vs_cloud, '')}"
            + (f"（云 {s.cloud_bottom:.2f} ~ {s.cloud_top:.2f}）" if s.cloud_top is not None else ""),
            f"- 所处云颜色：{_COLOR_CN.get(s.cloud_color, '')}",
            f"- 前方云（未来）：{_COLOR_CN.get(s.future_cloud_color, '')}",
            f"- 转换线/基准线：{_fmt(s.tenkan)} / {_fmt(s.kijun)}"
            + ("（转换线在上，短期偏多）" if s.tk_relation == "tenkan_above"
               else "（转换线在下，短期偏空）" if s.tk_relation == "tenkan_below" else ""),
            f"- 迟行线相对价格：{'上方（多）' if s.chikou_relation == 'above' else '下方（空）' if s.chikou_relation == 'below' else '持平/不足'}",
            "",
        ]

    if result.signals:
        lines.append("### 买卖信号（最近10个）")
        for sig in result.signals[-10:]:
            emoji = {"strong": "🔥", "medium": "⚡", "weak": "💡"}.get(sig.strength, "")
            lines.append(f"- **{sig.label}** {emoji} | {sig.time} | 价格={sig.price:.2f} | {sig.description}")
        lines.append("")

    lines.append("### 分析总结")
    lines.append(result.summary or "暂无总结")

    if result.recommendation:
        rec = result.recommendation
        lines.append("")
        lines.append("### 操作建议")
        lines.append(f"**{rec.action_label}**")
        for reason in rec.reasons:
            lines.append(f"- {reason}")
        if rec.caveats:
            lines.append(f"\n> {'；'.join(rec.caveats)}")

    return "\n".join(lines)


def _fmt(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else "N/A"
