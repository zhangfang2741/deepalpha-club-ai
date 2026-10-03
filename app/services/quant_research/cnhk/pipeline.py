"""A 股 / 港股 → StockInputs（与美股同一种输入），以及一致预期、汇率、收盘价。

- 一致预期一律整理成 FMP analyst-estimates 的字段（date / epsAvg / epsLow / epsHigh / revenueAvg / numAnalystsEps），
  这样 NTM 折算、前瞻增速、分析师人数门槛、EPS 修正快照都直接复用。
- 港股：报表（人民币）与预期（申报币种）都折成港元（股价币种）；**快照存申报币种原值**，
  否则汇率波动会被当成 EPS 修正。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from statistics import mean

import httpx
from redis.asyncio import Redis

from app.core.logging import logger
from app.services.quant_research.cnhk.etnet import EtnetForecast
from app.services.quant_research.cnhk.reports import CASH_FIELDS, INCOME_FIELDS, to_quarters
from app.services.quant_research.fmp import FmpClient
from app.services.quant_research.inputs import StockInputs, build_inputs
from app.services.skills.kline import fetch_kline

ESTIMATE_FRESH_DAYS = 180     # 只用近 6 个月更新过的券商预测（与 A 股「近六月平均」口径一致）
PRICE_DAYS = 420
FX_TTL = 12 * 3600


def _f(v) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


# ---------- 一致预期 ----------

def cn_estimates(f10: dict | None) -> list[dict]:
    """A 股 F10 盈利预测 → FMP 同形一致预期（只取预测年度；高低值取逐家机构预测的极值）。"""
    if not f10:
        return []
    per_year: dict[int, list[float]] = {}
    for r in f10.get("ycmx") or []:
        for i in range(1, 5):
            y, mark, eps = r.get(f"YEAR{i}"), r.get(f"YEAR_MARK{i}"), _f(r.get(f"EPS{i}"))
            if y and mark == "E" and eps is not None:
                per_year.setdefault(int(y), []).append(eps)
    out = []
    for r in f10.get("yctj_list") or []:
        if r.get("YEAR_MARK") != "E" or not r.get("YEAR"):
            continue
        y = int(r["YEAR"])
        vals = per_year.get(y, [])
        out.append({"date": f"{y}-12-31", "epsAvg": _f(r.get("EPS")), "epsLow": min(vals) if vals else None,
                    "epsHigh": max(vals) if vals else None, "revenueAvg": _f(r.get("TOTAL_OPERATE_INCOME")),
                    "ebitdaAvg": None, "ebitAvg": None, "numAnalystsEps": int(_f(r.get("EPS_COUNT")) or 0)})
    return sorted(out, key=lambda e: e["date"])


def fiscal_date(fy: int, fy_end: str) -> str:
    """财年（按截止年份）+ 年结日「MM-DD」→ 财年截止日。"""
    mm, dd = (fy_end or "12-31").split("-")[:2]
    if mm == "02" and dd in ("28", "29"):
        dd = "29" if (fy % 4 == 0 and (fy % 100 != 0 or fy % 400 == 0)) else "28"
    return f"{fy}-{mm.zfill(2)}-{dd.zfill(2)}"


def hk_estimates(fc: EtnetForecast | None, fy_end: str, as_of: date) -> list[dict]:
    """经济通逐家券商预测 → FMP 同形一致预期（申报币种原值，近 6 个月更新的券商取均值 / 极值 / 家数）。"""
    if fc is None:
        return []
    cutoff = as_of - timedelta(days=ESTIMATE_FRESH_DAYS)
    per_year: dict[int, list[float]] = {}
    for r in fc.rows:
        if r.eps is None or r.updated is None or r.updated < cutoff:
            continue
        per_year.setdefault(r.fiscal_year, []).append(r.eps)
    return [{"date": fiscal_date(y, fy_end), "epsAvg": round(mean(v), 6), "epsLow": min(v), "epsHigh": max(v),
             "revenueAvg": None, "ebitdaAvg": None, "ebitAvg": None, "numAnalystsEps": len(v)}
            for y, v in sorted(per_year.items())]


def scale_estimates(est: list[dict], k: float) -> list[dict]:
    """预期换币种（只换金额字段，分析师人数不变）。"""
    out = []
    for e in est:
        e2 = dict(e)
        for key in ("epsAvg", "epsLow", "epsHigh", "revenueAvg", "ebitdaAvg", "ebitAvg"):
            if e2.get(key) is not None:
                e2[key] = e2[key] * k
        out.append(e2)
    return out


# ---------- 汇率 ----------

async def cny_per(currencies: set[str], *, client: httpx.AsyncClient, redis: Redis | None,
                  priority: str = "batch") -> dict[str, float]:
    """{币种: 1 单位折合多少人民币}（CNY 恒为 1）；取不到的币种不出现在结果里。"""
    out: dict[str, float] = {"CNY": 1.0}
    fmp = FmpClient(client, redis, priority)  # type: ignore[arg-type]
    for cur in sorted(currencies - {"CNY"}):
        key = f"quant:fx:{cur}CNY"
        if redis is not None:
            try:
                cached = await redis.get(key)
                if cached:
                    out[cur] = float(cached)
                    continue
            except Exception as e:  # noqa: BLE001
                logger.warning("quant_fx_cache_read_failed", currency=cur, error=str(e))
        data = await fmp.get("quote-short", symbol=f"{cur}CNY")
        rate = _f(data[0].get("price")) if isinstance(data, list) and data else None
        if rate is None or rate <= 0:
            logger.warning("quant_fx_unavailable", currency=cur)
            continue
        out[cur] = rate
        if redis is not None:
            try:
                await redis.set(key, str(rate), ex=FX_TTL)
            except Exception as e:  # noqa: BLE001
                logger.warning("quant_fx_cache_write_failed", currency=cur, error=str(e))
    return out


# ---------- 收盘价 ----------

async def fetch_prices(symbol: str, as_of: date, redis: Redis | None) -> list[dict]:
    """前复权日收盘价（旧 → 新），整理成 build_inputs 需要的 [{date, price}]；取不到返回空。"""
    try:
        bars = await fetch_kline(None, symbol, (as_of - timedelta(days=PRICE_DAYS)).isoformat(), as_of.isoformat(),
                                 redis=redis)
    except Exception as e:  # noqa: BLE001 单只拉价失败当天不重算它
        logger.warning("quant_cnhk_price_failed", symbol=symbol, error=str(e))
        return []
    return [{"date": b["time"], "price": b["close"]} for b in bars if b.get("close")]


# ---------- 组装 ----------

def _scale_report(r: dict, k: float) -> dict:
    out = dict(r)
    for f in INCOME_FIELDS + CASH_FIELDS:
        if out.get(f) is not None:
            out[f] = out[f] * k
    return out


def _scale_balance(b: dict | None, k: float) -> dict | None:
    if b is None:
        return None
    out = dict(b)
    for f in ("totalAssets", "totalStockholdersEquity", "totalDebt", "cashAndShortTermInvestments"):
        if out.get(f) is not None:
            out[f] = out[f] * k
    return out


def build_cnhk_inputs(*, market: str, symbol: str, name: str | None, sector: str, as_of: date,
                      reports: list[dict], balance: dict | None, estimates: list[dict], prices: list[dict],
                      shares: float | None, amount_scale: float = 1.0, estimate_scale: float = 1.0,
                      fx: dict | None = None) -> StockInputs:
    """累计报告 + 预期 + 收盘价 → StockInputs。amount_scale / estimate_scale 把报表、预期换成股价币种。"""
    reps = [_scale_report(r, amount_scale) for r in reports] if amount_scale != 1.0 else reports
    income, cash = to_quarters(reps)
    inp = build_inputs(symbol=symbol, as_of=as_of, sector_key=sector, income=income, cash=cash,
                       balance=_scale_balance(balance, amount_scale),
                       estimates=scale_estimates(estimates, estimate_scale) if estimate_scale != 1.0 else estimates,
                       prices=prices, name=name)
    return replace(inp, shares_diluted=shares, market=market, fx=fx)


def estimate_rows_for(market: str, symbol: str, snapshot_date: date, estimates: list[dict]) -> list[dict]:
    """一致预期快照行（申报币种原值）；复用美股的字段映射。"""
    from app.services.quant_research.batch import estimate_rows

    return estimate_rows(market, symbol, snapshot_date, estimates)
