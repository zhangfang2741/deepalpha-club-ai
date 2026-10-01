"""外部 EPS 一致预期趋势（当前 / 30 天前 / 90 天前），只在自有快照攒满 90 天前做过渡。

数据来自 yfinance 的 eps_trend（0y = 本财年、+1y = 下财年）。文案里不出现数据源名（copy.FORBIDDEN）。
限速：进程内并发 _CONCURRENCY、每次请求后停 _PAUSE 秒；单只失败只记日志、该股这一项保持 missing。
"""

from __future__ import annotations

import asyncio

from app.core.logging import logger
from app.services.quant_research.revisions import FULL_DAYS, EpsTrend

_CONCURRENCY = 4
_PAUSE = 0.25
_COLUMNS = {0: "current", 30: "30daysAgo", 90: "90daysAgo"}
_gate = asyncio.Semaphore(_CONCURRENCY)


def _num(v: object) -> float | None:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # 去掉 NaN


def parse_eps_trend(df: object) -> EpsTrend | None:
    """eps_trend DataFrame → EpsTrend；缺本财年当前值视为无数据。"""
    rows: dict[str, dict[int, float]] = {}
    for period in ("0y", "+1y"):
        try:
            row = df.loc[period]  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 结构不符 / 缺行
            rows[period] = {}
            continue
        rows[period] = {d: v for d, col in _COLUMNS.items() if (v := _num(row.get(col))) is not None}
    if 0 not in rows["0y"]:
        return None
    return EpsTrend(fy1=rows["0y"], fy2=rows["+1y"])


def _fetch_blocking(symbol: str) -> EpsTrend | None:
    import yfinance as yf

    return parse_eps_trend(yf.Ticker(symbol.replace(".", "-")).eps_trend)


async def fetch_eps_trend(symbol: str) -> EpsTrend | None:
    """拉取单只股票的 EPS 趋势；失败返回 None。"""
    async with _gate:
        try:
            return await asyncio.to_thread(_fetch_blocking, symbol)
        except Exception as e:  # noqa: BLE001 外部源不可用只影响过渡期这一项
            logger.warning("quant_eps_trend_failed", symbol=symbol, error=str(e))
            return None
        finally:
            await asyncio.sleep(_PAUSE)


def needs_trend(history_days: int) -> bool:
    """自有快照不满最长回看期（90 天）才需要外部趋势。"""
    return history_days < FULL_DAYS
