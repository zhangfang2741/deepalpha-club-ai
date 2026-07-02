"""威科夫方法论 LangGraph 工具：让 AI Agent 能够用威科夫方法分析股票。"""
from __future__ import annotations

from app.cache.client import current_redis
from app.core.logging import logger
from app.services.skills.kline import fetch_kline
from app.services.wyckoff.analyzer import WyckoffAnalyzer

_analyzer = WyckoffAnalyzer()


async def wyckoff_analysis_tool(
    symbol: str,
    start_date: str,
    end_date: str,
    freq: str = "daily",
) -> str:
    """使用威科夫方法论（The Wyckoff Methodology）对股票进行技术分析。

    分析内容：
    - 识别交易区间（trading range）的支撑与阻力
    - 判定吸筹 / 拉升 / 派发 / 下跌四大市场周期阶段及区间内 A–E 子阶段
    - 标记威科夫事件（SC 卖出高潮 / AR 自动反弹 / ST 二次测试 / Spring 弹簧 /
      SOS 强势信号 / UT 冲高回落 / UTAD / SOW 弱势信号 / LPS / LPSY 等）
    - 应用三大定律（供求关系 / 因果关系 / 量价关系）

    返回详细的文本分析报告，供用户参考投资决策。
    """
    logger.info("wyckoff_tool_called", symbol=symbol, start=start_date, end=end_date)

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
    return _analyzer.to_text_report(result)
