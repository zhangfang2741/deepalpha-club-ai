"""A 股 / 港股行业强弱（regime 行业级）：每个本土行业用「市值最大的几只成分股等权合成的行业指数」。

不用行业 ETF：A 股 / 港股的行业 ETF 零散（申万 31 个行业里不少没有干净的 ETF，Yahoo 上标的名称也难核对），
而成分股与行业归属就是雷达给信号打标签用的同一份东财数据，31 个申万行业 / 12 个恒生行业都能覆盖。
行业指数 = 成分股日收益的等权平均（只用当天与前一天都有价格的成分股），高低价按成分股平均振幅还原，
成交量用成交额合计；与大盘（基准 ETF）一起喂给美股同一套行业管线（`sector_pipeline.compute_sector_regimes`：
每个行业独立走-前向 HMM，特征 = 行业收益 / 波动 / 波动比 / 相对大盘强弱 / CMF）。
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

import numpy as np
from sqlmodel import Session, select

from app.core.logging import logger
from app.models.regime_market_sector_features import RegimeMarketSectorFeatures
from app.services.regime.cnhk import MARKET_CONFIGS, vol_ratio
from app.services.regime.fetcher import SectorMarketData
from app.services.regime.sector_pipeline import SectorRegimeRecord, compute_sector_regimes

TOP_N = 8              # 每个行业取市值最大的几只
MIN_CONSTITUENTS = 3   # 少于这个只数的行业不出强弱（成分太少，指数就是个股）
_MIN_DAY_CONSTITUENTS = 2
_CONCURRENCY = 3
_GAP_SECONDS = 0.5


def pick_constituents(market: str, meta: dict[str, object], top_n: int = TOP_N) -> dict[str, list[str]]:
    """{行业: [市值最大的 top_n 只的 Yahoo 代码]}（纯函数）。

    行业口径与雷达标签一致（`signal_radar.sectors`）：A 股申万一级、港股恒生一级。
    A 股剔除 ST / 退市整理；港股剔除人民币柜台（8 开头的 5 位代码）。
    """
    from app.services.signal_radar.sectors import cn_tags_from_meta, hk_tags_from_meta
    from app.utils.market import fmp_symbol

    tags = cn_tags_from_meta(meta) if market == "cn" else hk_tags_from_meta(meta)
    by_sector: dict[str, list[tuple[float, str]]] = {}
    for code, sector in tags.items():
        m = meta[code]
        cap = getattr(m, "market_cap", None)
        name = str(getattr(m, "name", "") or "")
        if not cap or ("ST" in name.upper() or "退" in name):
            continue
        if market == "hk" and code.startswith("8"):
            continue
        by_sector.setdefault(sector, []).append((float(cap), code))
    out: dict[str, list[str]] = {}
    for sector, items in by_sector.items():
        items.sort(reverse=True)
        out[sector] = [fmp_symbol(code) for _, code in items[:top_n]]
    return out


def build_sector_index(bars_list: list[list[dict]], spine: list[str]) -> dict[str, np.ndarray] | None:
    """成分股日线 → 行业指数的 close / high / low / volume（在 spine 日期上，纯函数）。

    成分股在 spine 上没有数据的日期不参与当天平均；某天可用成分股少于 2 只则指数当天不变且 close 置 NaN，
    由下游 valid_mask 自动跳过。返回 None = 可用成分股不足。
    """
    maps = [{r["time"]: r for r in bars if r.get("close")} for bars in bars_list if bars]
    if len(maps) < MIN_CONSTITUENTS:
        return None
    n = len(spine)
    close = np.full(n, np.nan)
    high = np.full(n, np.nan)
    low = np.full(n, np.nan)
    volume = np.zeros(n)
    level = 1.0
    started = False
    for i, d in enumerate(spine):
        rets, hi_r, lo_r, turn = [], [], [], 0.0
        for m in maps:
            r = m.get(d)
            if r is None:
                continue
            prev = m.get(spine[i - 1]) if i > 0 else None
            if prev is not None and prev["close"] > 0:
                rets.append(r["close"] / prev["close"] - 1.0)
            if r["close"] > 0:
                hi_r.append(r["high"] / r["close"])
                lo_r.append(r["low"] / r["close"])
                turn += r["close"] * float(r.get("volume") or 0.0)
        if len(hi_r) < _MIN_DAY_CONSTITUENTS:
            continue
        if rets and started:
            level *= 1.0 + float(np.mean(rets))
        started = True
        close[i] = level
        high[i] = level * float(np.mean(hi_r))
        low[i] = level * float(np.mean(lo_r))
        volume[i] = turn
    if np.isfinite(close).sum() == 0:
        return None
    return {"close": close, "high": high, "low": low, "volume": volume}


def build_sector_market_data(
    market: str, bench_bars: list[dict], constituent_bars: dict[str, dict[str, list[dict]]],
) -> SectorMarketData:
    """大盘（基准 ETF）日线 + 各行业成分股日线 → `SectorMarketData`（纯函数）。

    时间轴 = 基准 ETF 的交易日；`vix_close` 槽装基准的短 / 长期波动比（与大盘状态同口径）。
    """
    spine = sorted({r["time"] for r in bench_bars if r.get("close")})
    if not spine:
        raise RuntimeError("缺少基准行情，无法计算行业状态")
    bench = {r["time"]: r for r in bench_bars if r.get("close")}
    bench_close = np.array([bench[d]["close"] for d in spine], dtype=float)
    sectors: dict[str, dict[str, np.ndarray]] = {}
    for sector, by_symbol in constituent_bars.items():
        idx = build_sector_index(list(by_symbol.values()), spine)
        if idx is not None:
            sectors[sector] = idx
    if not sectors:
        raise RuntimeError("所有行业成分股行情缺失，无法计算行业状态")
    return SectorMarketData(dates=[date.fromisoformat(d) for d in spine], vix_close=vol_ratio(bench_close),
                            market_close=bench_close, sectors=sectors)


def _fetch_all(symbols: list[str], lookback_days: int) -> dict[str, list[dict]]:
    """并发（上限 3）拉成分股日线（同步入口，在子进程里调用）；拉不到的给空列表。"""
    from app.services.skills.kline import _fetch_yahoo

    end = date.today()
    start = (end - timedelta(days=lookback_days)).isoformat()

    async def _all() -> dict[str, list[dict]]:
        sem = asyncio.Semaphore(_CONCURRENCY)
        out: dict[str, list[dict]] = {}

        async def one(sym: str) -> None:
            async with sem:
                try:
                    out[sym] = await _fetch_yahoo(sym, start, end.isoformat(), "1d")
                except Exception as e:  # noqa: BLE001
                    logger.warning("regime_cnhk_sector_fetch_failed", symbol=sym, error=str(e))
                    out[sym] = []
                await asyncio.sleep(_GAP_SECONDS)

        await asyncio.gather(*(one(s) for s in symbols))
        return out

    return asyncio.run(_all())


def _load_meta(market: str) -> dict[str, object]:
    """整市场元数据（行业 + 总市值），东财数据中心；同步入口。"""
    import httpx

    from app.services.quant_research.cnhk import cn_source, hk_source
    from app.services.quant_research.cnhk.http import _UA

    async def _go() -> dict[str, object]:
        async with httpx.AsyncClient(timeout=60, headers={"User-Agent": _UA}, trust_env=False) as client:
            if market == "cn":
                return dict(await cn_source.fetch_market_meta(client))
            return dict(await hk_source.fetch_meta(client, date.today()))

    return asyncio.run(_go())


def persist_sector_records(session: Session, market: str, by_sector: dict[str, list[SectorRegimeRecord]]) -> int:
    """按 (market, sector, trade_date) upsert，返回写入 / 更新条数。"""
    existing = {
        (r.sector, r.trade_date): r
        for r in session.exec(select(RegimeMarketSectorFeatures).where(RegimeMarketSectorFeatures.market == market)).all()
    }
    written = 0
    for recs in by_sector.values():
        for rec in recs:
            if rec.p_risk_on is None and rec.rs_vs_market is None:
                continue  # 前置窗口全空的行不落库
            row = existing.get((rec.sector, rec.trade_date))
            if row is None:
                row = RegimeMarketSectorFeatures(market=market, sector=rec.sector, trade_date=rec.trade_date)
                session.add(row)
            row.sector_ret = rec.sector_ret
            row.sector_vol = rec.sector_vol
            row.vol_ratio = rec.vix
            row.rs_vs_market = rec.rs_vs_market
            row.sector_cmf = rec.sector_cmf
            row.p_risk_on = rec.p_risk_on
            row.p_neutral = rec.p_neutral
            row.p_risk_off = rec.p_risk_off
            row.regime_label = rec.regime_label
            row.confirmed_label = rec.confirmed_label
            row.params_version = rec.params_version
            written += 1
    session.commit()
    return written


def run_sector_stage(session: Session, market: str, lookback_days: int = 1500) -> dict:
    """取元数据 → 选成分股 → 拉行情 → 合成行业指数 → 逐行业算状态 → 落库，返回摘要。

    回看约 4 年：每个行业的走-前向 HMM 要逐月重估，耗时随历史长度增长（实测 5 年约 50 秒 / 行业，4 年约 15 秒），
    A 股 31 个行业约 8 分钟、港股 12 个约 3 分钟；状态从约 2024 年起有。
    """
    cfg = MARKET_CONFIGS[market]
    picks = pick_constituents(market, _load_meta(market))
    symbols = sorted({s for syms in picks.values() for s in syms} | {cfg.benchmark})
    logger.info("regime_cnhk_sector_start", market=market, sectors=len(picks), symbols=len(symbols))
    bars = _fetch_all(symbols, lookback_days)
    data = build_sector_market_data(
        market, bars.get(cfg.benchmark, []),
        {sec: {s: bars.get(s, []) for s in syms} for sec, syms in picks.items()},
    )
    by_sector = compute_sector_regimes(data)
    written = persist_sector_records(session, market, by_sector)
    logger.info("regime_cnhk_sector_done", market=market, sectors=len(by_sector), written=written)
    return {"market": market, "sectors": len(by_sector), "written": written}
