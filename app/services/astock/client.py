"""A 股数据源客户端（纯外部调用，不碰 DB / Redis）。

- 日 K 线：直连东方财富行情接口（前复权）。参数与 app/services/skills/kline.py 一致：
  klt=101 日线，fqt=1 前复权；trust_env=False 避免 .env 里给 LLM API 用的代理断连。
- 实时快照 / 基本面 / 搜索：akshare（阻塞式，包在线程里执行）。
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.logging import logger
from app.services.astock.symbols import akshare_code, eastmoney_secid, normalize_symbol

_EASTMONEY_KLINE_URL = "https://33.push2his.eastmoney.com/api/qt/stock/kline/get"


class AStockDataUnavailable(Exception):
    """行情数据源暂时不可用（网络不可达或被限流）。"""


def _fetch_kline_sync(secid: str, start: str, end: str) -> list[dict[str, Any]]:
    """同步拉取东方财富前复权日 K 线。"""
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        # 日期、开盘、收盘、最高、最低、成交量、成交额
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "klt": "101",
        "fqt": "1",
        "beg": start.replace("-", ""),
        "end": end.replace("-", ""),
    }

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=6),
        reraise=True,
    )
    def _do() -> list[dict[str, Any]]:
        resp = httpx.get(_EASTMONEY_KLINE_URL, params=params, timeout=30, trust_env=False)
        resp.raise_for_status()
        data = (resp.json() or {}).get("data")
        if not data or not data.get("klines"):
            return []
        bars: list[dict[str, Any]] = []
        for line in data["klines"]:
            parts = line.split(",")
            if len(parts) < 6:
                continue
            bars.append(
                {
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                }
            )
        bars.sort(key=lambda b: b["date"])
        return bars

    try:
        return _do()
    except (httpx.RemoteProtocolError, httpx.TransportError) as exc:
        logger.warning("astock_kline_unavailable", secid=secid, error=str(exc))
        raise AStockDataUnavailable("行情数据源暂时不可用（可能被限流），请稍后重试") from exc


async def fetch_daily_bars(symbol: str, start: str, end: str) -> list[dict[str, Any]]:
    """异步拉取某标的 [start, end] 区间的前复权日 K 线（按日期升序）。

    Args:
        symbol: 任意写法的 A 股代码（内部会归一化）。
        start: 起始日 YYYY-MM-DD。
        end: 结束日 YYYY-MM-DD。
    """
    secid = eastmoney_secid(symbol)
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return await loop.run_in_executor(pool, _fetch_kline_sync, secid, start, end)


async def fetch_close_on_or_after(symbol: str, target_date: str, window_days: int = 14) -> Optional[dict[str, Any]]:
    """取 target_date 当天或其后第一个交易日的日 K 线（用于回测到期结算）。

    从 target_date 起向后取 window_days 自然日的 K 线，返回首个 date >= target_date 的 bar。
    若窗口内无数据（未到期或停牌）返回 None。
    """
    from datetime import datetime, timedelta

    end_dt = datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=window_days)
    bars = await fetch_daily_bars(symbol, target_date, end_dt.strftime("%Y-%m-%d"))
    for bar in bars:
        if bar["date"] >= target_date:
            return bar
    return None


def _fetch_quote_sync(code: str, symbol: str) -> Optional[dict[str, Any]]:
    """同步：用 akshare 取实时快照（东财现价列表里挑出该代码）。"""
    import akshare as ak

    df = ak.stock_zh_a_spot_em()
    row = df[df["代码"] == code]
    if row.empty:
        return None
    r = row.iloc[0]

    def _num(key: str) -> Optional[float]:
        try:
            val = r.get(key)
            return None if val is None else float(val)
        except (TypeError, ValueError):
            return None

    return {
        "symbol": symbol,
        "name": str(r.get("名称", "")),
        "price": _num("最新价"),
        "change_pct": _num("涨跌幅"),
        "change": _num("涨跌额"),
        "volume": _num("成交量"),
        "amount": _num("成交额"),
        "turnover_rate": _num("换手率"),
        "pe_ttm": _num("市盈率-动态"),
        "pb": _num("市净率"),
        "market_cap": _num("总市值"),
    }


async def fetch_quote(symbol: str) -> Optional[dict[str, Any]]:
    """异步取实时快照。数据源不可用时抛 AStockDataUnavailable。"""
    norm = normalize_symbol(symbol)
    code = akshare_code(norm)
    loop = asyncio.get_event_loop()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return await loop.run_in_executor(pool, _fetch_quote_sync, code, norm)
    except Exception as exc:  # akshare 内部异常五花八门，统一转成可读错误
        logger.warning("astock_quote_unavailable", symbol=norm, error=str(exc))
        raise AStockDataUnavailable("实时行情数据源暂时不可用，请稍后重试") from exc


def _fetch_fundamental_sync(code: str, symbol: str) -> dict[str, Any]:
    """同步：用 akshare 取个股关键指标（估值/基本面）。"""
    import akshare as ak

    result: dict[str, Any] = {"symbol": symbol, "indicators": {}}
    # 个股信息（名称、行业、总市值等）
    try:
        info = ak.stock_individual_info_em(symbol=code)
        result["profile"] = {
            str(row["item"]): row["value"] for _, row in info.iterrows()
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("astock_profile_unavailable", symbol=symbol, error=str(exc))
        result["profile"] = {}
    return result


async def fetch_fundamental(symbol: str) -> dict[str, Any]:
    """异步取基本面/关键指标。数据源不可用时抛 AStockDataUnavailable。"""
    norm = normalize_symbol(symbol)
    code = akshare_code(norm)
    loop = asyncio.get_event_loop()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return await loop.run_in_executor(pool, _fetch_fundamental_sync, code, norm)
    except Exception as exc:  # noqa: BLE001
        logger.warning("astock_fundamental_unavailable", symbol=norm, error=str(exc))
        raise AStockDataUnavailable("基本面数据源暂时不可用，请稍后重试") from exc
