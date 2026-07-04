"""机构资金信号数据抓取（FMP stable API + yfinance 期权）。

单源失败返回空/None，不抛异常——由 calculator 决定降级为 partial。
"""
import datetime

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.services.institutional_signals.constants import (
    OPTION_EXPIRY_MAX_DAYS,
    OPTION_EXPIRY_MIN_COUNT,
)

_FMP_STABLE = "https://financialmodelingprep.com/stable"
_TIMEOUT = 15


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> list | dict | None:
    try:
        resp = await client.get(
            f"{_FMP_STABLE}/{path}",
            params={**params, "apikey": settings.FMP_API_KEY},
        )
        if resp.status_code != 200:
            logger.warning("institutional_signals_fetch_non200", path=path, status=resp.status_code)
            return None
        data = resp.json()
        if isinstance(data, dict) and "Error Message" in data:
            return None
        return data
    except Exception as e:
        logger.warning("institutional_signals_fetch_error", path=path, error=str(e))
        return None


async def fetch_profile(client: httpx.AsyncClient, symbol: str) -> dict | None:
    """公司档案（取公司名）。"""
    data = await _get(client, "profile", {"symbol": symbol})
    if isinstance(data, list) and data:
        return data[0]
    return None


async def fetch_price_target_summary(client: httpx.AsyncClient, symbol: str) -> dict | None:
    """目标价汇总（近月/季/年均值 + 家数）。"""
    data = await _get(client, "price-target-summary", {"symbol": symbol})
    if isinstance(data, list) and data:
        return data[0]
    return None


async def fetch_grades_historical(client: httpx.AsyncClient, symbol: str) -> list[dict]:
    """评级历史（各月强买/买/持有/卖出家数）。"""
    data = await _get(client, "grades-historical", {"symbol": symbol, "limit": 12})
    return data if isinstance(data, list) else []


def _extract_symbols(data) -> list[str]:
    if not isinstance(data, list):
        return []
    out = []
    for r in data:
        sym = (r.get("symbol") or "").strip().upper()
        if sym and sym.isalpha():  # 过滤含点号的多类股（如 BRK.B）避免期权/接口不一致
            out.append(sym)
    return out


async def fetch_sp500_symbols(client: httpx.AsyncClient) -> list[str]:
    """S&P 500 成分股代码（动态）。失败返回空 → 由调用方降级到 fallback。"""
    return _extract_symbols(await _get(client, "sp500-constituent", {}))


async def fetch_nasdaq100_symbols(client: httpx.AsyncClient) -> list[str]:
    """纳斯达克 100（QQQ 成分股）代码（动态）。失败返回空 → 降级到 fallback。"""
    return _extract_symbols(await _get(client, "nasdaq-constituent", {}))


async def fetch_analyst_estimate(client: httpx.AsyncClient, symbol: str) -> dict | None:
    """最新一期分析师一致预期（EPS/营收），用于每日快照记录修正趋势。"""
    data = await _get(client, "analyst-estimates", {"symbol": symbol, "limit": 1})
    if isinstance(data, list) and data:
        return data[0]
    return None


async def fetch_earnings(client: httpx.AsyncClient, symbol: str) -> list[dict]:
    """财报日程（含历史 epsActual/epsEstimated 与未来财报日）。"""
    data = await _get(client, "earnings-calendar", {"symbol": symbol, "limit": 16})
    return data if isinstance(data, list) else []


async def fetch_insider_statistics(client: httpx.AsyncClient, symbol: str) -> list[dict]:
    """内部人交易季度统计（acquired/disposed、totalPurchases/totalSales）。"""
    data = await _get(client, "insider-trading/statistics", {"symbol": symbol})
    return data if isinstance(data, list) else []


async def fetch_price_history(client: httpx.AsyncClient, symbol: str, from_: str, to: str) -> list[dict]:
    """日线 EOD，按日期升序，标准化字段。"""
    data = await _get(client, "historical-price-eod/full",
                      {"symbol": symbol, "from": from_, "to": to})
    if not isinstance(data, list):
        return []
    rows = [
        {"date": r["date"], "open": r.get("open", 0), "high": r.get("high", 0),
         "low": r.get("low", 0), "close": r.get("close", 0), "volume": r.get("volume", 0)}
        for r in data if r.get("date")
    ]
    return sorted(rows, key=lambda x: x["date"])


# ── 期权（yfinance，同步 → calculator 中用 asyncio.to_thread 调用）──────────

def _atm_iv(df, spot: float) -> float | None:
    """取行权价最接近现价的合约的隐含波动率。"""
    if df is None or df.empty or not spot:
        return None
    idx = (df["strike"] - spot).abs().idxmin()
    iv = df.loc[idx, "impliedVolatility"]
    try:
        iv = float(iv)
    except (TypeError, ValueError):
        return None
    return iv if iv == iv and iv > 0 else None  # 过滤 NaN 与非正值


def fetch_option_metrics(symbol: str, spot: float) -> dict | None:
    """聚合近月期权链，返回 Call/Put 成交量、OI 与 ATM IV。

    同步函数（yfinance 底层为 requests），calculator 用 asyncio.to_thread 调用。
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        expiries = list(getattr(ticker, "options", []) or [])
        if not expiries:
            return None

        today = datetime.date.today()
        dated = []
        for e in expiries:
            try:
                d = datetime.date.fromisoformat(e)
            except ValueError:
                continue
            days = (d - today).days
            if days >= 0:
                dated.append((e, days))
        if not dated:
            return None

        within = [e for e, days in dated if days <= OPTION_EXPIRY_MAX_DAYS]
        if len(within) < OPTION_EXPIRY_MIN_COUNT:
            within = [e for e, _ in dated[:OPTION_EXPIRY_MIN_COUNT]]

        call_vol = put_vol = call_oi = put_oi = 0
        ivs: list[float] = []
        for e in within:
            chain = ticker.option_chain(e)
            calls, puts = chain.calls, chain.puts
            call_vol += int(calls["volume"].fillna(0).sum())
            put_vol += int(puts["volume"].fillna(0).sum())
            call_oi += int(calls["openInterest"].fillna(0).sum())
            put_oi += int(puts["openInterest"].fillna(0).sum())
            for iv in (_atm_iv(calls, spot), _atm_iv(puts, spot)):
                if iv is not None:
                    ivs.append(iv)

        return {
            "call_vol": call_vol,
            "put_vol": put_vol,
            "call_oi": call_oi,
            "put_oi": put_oi,
            "atm_iv": sum(ivs) / len(ivs) if ivs else 0.0,
            "expiries_used": within,
        }
    except Exception as e:
        logger.warning("institutional_signals_option_fetch_error", symbol=symbol, error=str(e))
        return None
