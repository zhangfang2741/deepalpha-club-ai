"""A股/港股行情工具（akshare 同步库 → asyncio.to_thread 包装成异步工具）。

约定：任何失败都不抛异常，返回「工具失败: 原因」字符串，让 LLM 自行换
搜索工具兜底（Agentic 生成的容错约定）。
"""

import asyncio
from typing import Any

import akshare as ak
from langchain_core.tools import tool

from app.core.logging import logger


def _fmt_row(name: str, price: Any, pct: Any) -> str:
    pct_f = float(pct or 0)
    sign = "+" if pct_f >= 0 else ""
    return f"- {name}: {price}（{sign}{pct_f:.2f}%）"


def _fmt_rows(df: Any, wanted: set[str]) -> list[str]:
    return [
        _fmt_row(str(r["名称"]), r["最新价"], r["涨跌幅"])
        for _, r in df.iterrows()
        if r["名称"] in wanted
    ]


def _fetch_cn_index():
    return ak.stock_zh_index_spot_em(symbol="沪深重要指数")


@tool
async def cn_index_snapshot() -> str:
    """获取A股主要指数最新快照（上证指数、深证成指、创业板指）与两市成交额。"""
    try:
        df = await asyncio.to_thread(_fetch_cn_index)
        if df is None or df.empty:
            return "未查到A股指数数据"
        lines = _fmt_rows(df, {"上证指数", "深证成指", "创业板指"})
        # 指数存在成分股重叠，不能把所有指数成交额相加。
        turnovers = {
            str(r["名称"]): r.get("成交额") for _, r in df.iterrows()
            if r["名称"] in {"上证指数", "深证成指"}
        }
        if len(turnovers) == 2 and all(value is not None for value in turnovers.values()):
            total = sum(float(value) for value in turnovers.values() if value is not None)
            lines.append(f"- 沪深两市成交额: {total / 1e8:.0f} 亿元")
        return "\n".join(lines) or "未查到A股指数数据"
    except Exception as exc:  # noqa: BLE001 —— 工具层约定吞异常，供 LLM 换工具兜底
        logger.exception("morning_report_tool_failed", tool="cn_index_snapshot")
        return f"工具失败: {exc}"


def _fetch_hsgt():
    return ak.stock_hsgt_fund_flow_summary_em()


@tool
async def cn_north_flow() -> str:
    """获取沪深港通资金流向汇总（北向/南向净流入最新一日，单位亿元）。"""
    try:
        df = await asyncio.to_thread(_fetch_hsgt)
        if df is None or df.empty:
            return "未查到沪深港通资金数据"
        return "\n".join(
            f"- {r['板块']}（{r['资金方向']}）: 净流入 {r['成交净买额']} 亿元" for _, r in df.iterrows()
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("morning_report_tool_failed", tool="cn_north_flow")
        return f"工具失败: {exc}"


def _fetch_hk_index():
    return ak.stock_hk_index_spot_em()


@tool
async def hk_index_snapshot() -> str:
    """获取港股主要指数最新快照（恒生指数、恒生科技指数）。"""
    try:
        df = await asyncio.to_thread(_fetch_hk_index)
        if df is None or df.empty:
            return "未查到港股指数数据"
        lines = _fmt_rows(df, {"恒生指数", "恒生科技指数"})
        return "\n".join(lines) or "未查到港股指数数据"
    except Exception as exc:  # noqa: BLE001
        logger.exception("morning_report_tool_failed", tool="hk_index_snapshot")
        return f"工具失败: {exc}"


AKSHARE_TOOLS = [cn_index_snapshot, cn_north_flow, hk_index_snapshot]


# 美股主要指数快照——FMP quote 端点额度/订阅受限时的兜底数据源，不依赖 FMP。
US_TICKERS: dict[str, str] = {
    "标普500": "^GSPC",
    "道琼斯": "^DJI",
    "纳斯达克综合": "^IXIC",
    "罗素2000": "^RUT",
    "VIX恐慌指数": "^VIX",
    "10年期美债收益率": "^TNX",
}


def _fetch_us_snapshot() -> Any:
    import yfinance as yf

    return yf.download(
        list(US_TICKERS.values()),
        period="5d",
        interval="1d",
        progress=False,
        group_by="ticker",
        auto_adjust=False,
    )


@tool
async def us_index_snapshot() -> str:
    """获取美股主要指数最新快照（标普500/道指/纳指/罗素2000/VIX/10年期美债收益率），用于 FMP 行情不可用时兜底。"""
    try:
        df = await asyncio.to_thread(_fetch_us_snapshot)
        if df is None or df.empty:
            return "未查到美股指数数据"
        lines: list[str] = []
        for name, symbol in US_TICKERS.items():
            try:
                closes = df[symbol]["Close"].dropna()
            except KeyError:
                continue
            if len(closes) < 2:
                continue
            latest, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
            if prev == 0:
                continue
            pct = (latest - prev) / prev * 100
            sign = "+" if pct >= 0 else ""
            lines.append(f"- {name}: {latest:.2f}（{sign}{pct:.2f}%，较上一交易日）")
        return "\n".join(lines) or "未查到美股指数数据"
    except Exception as exc:  # noqa: BLE001 —— 工具层约定吞异常，供 LLM 换工具兜底
        logger.exception("morning_report_tool_failed", tool="us_index_snapshot")
        return f"工具失败: {exc}"
