"""A 股 / 港股大盘状态（regime）：与美股同一条管线，换成各自市场的 ETF 篮子。

复用美股的特征（`features.build_feature_series`）、走-前向 HMM（`engine.run_walk_forward`）与
后验计算（`pipeline.compute_regime_from_market`），这里只做「取数 + 对齐 + 落库」：

- 基准（对应美股的纳指）：A 股沪深 300 ETF、港股盈富基金。
- 进攻 / 防御 / 现金三个等权篮子：见 `MARKET_CONFIGS`。选 ETF 的标准是 Yahoo 有完整日线、
  流动性足够、现金篮子年化波动在 2% 以内（实测国债 ETF 约 1.5%、短融 ETF 约 0.7%、港股短债约 0.8%）。
- 两个市场没有可用的波动率指数（VIX），特征里的 `vix` 槽换成「20 日 / 60 日已实现波动比」：
  >1 表示近期波动在放大，口径同样是越大越偏避险，标签打分权重不变。
- 数据源 Yahoo（`skills.kline._fetch_yahoo`，与详情页同源，海外可达）。取数逐只串行并留间隔，避免被限流。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from sqlmodel import Session, select

from app.core.logging import logger
from app.models.regime_market_features import RegimeMarketFeatures
from app.services.regime.fetcher import RegimeMarketData
from app.services.regime.indicators import realized_vol
from app.services.regime.pipeline import RegimeDailyRecord, compute_regime_from_market

SHORT_VOL_WINDOW = 20
LONG_VOL_WINDOW = 60
_FETCH_GAP_SECONDS = 1.0


@dataclass(frozen=True)
class MarketConfig:
    """一个市场的三篮子配置（代码为 Yahoo 形态）。"""

    benchmark: str
    offense: tuple[str, ...]
    defense: tuple[str, ...]
    cash: tuple[str, ...]

    @property
    def symbols(self) -> list[str]:
        """基准 + 三个篮子的全部代码（去重、保持顺序）。"""
        seen: set[str] = set()
        return [s for s in (self.benchmark, *self.offense, *self.defense, *self.cash) if not (s in seen or seen.add(s))]


MARKET_CONFIGS: dict[str, MarketConfig] = {
    "cn": MarketConfig(
        benchmark="510300.SS",                                   # 沪深 300 ETF
        offense=("159915.SZ", "588000.SS", "512480.SS"),         # 创业板 / 科创 50 / 半导体
        defense=("510880.SS", "159928.SZ", "512010.SS"),         # 红利 / 消费 / 医药
        cash=("511010.SS", "511360.SS"),                         # 国债 / 短融
    ),
    "hk": MarketConfig(
        benchmark="2800.HK",                                     # 盈富基金
        offense=("3033.HK", "2801.HK"),                          # 恒生科技 / 中国（MSCI）
        defense=("3110.HK",),                                    # 高息
        cash=("3053.HK",),                                       # 短债
    ),
}

# 收盘后触发的 UTC 时刻（A 股 15:00 CST = 07:00 UTC，港股 16:00 HKT = 08:00 UTC，各留 30 分钟数据缓冲）
CLOSE_HOUR_UTC: dict[str, int] = {"cn": 7, "hk": 8}
TRIGGER_UTC: dict[str, tuple[int, int]] = {"cn": (7, 40), "hk": (8, 40)}


def vol_ratio(close: np.ndarray) -> np.ndarray:
    """短期 / 长期已实现波动比（前 LONG_VOL_WINDOW 个为 NaN）。"""
    close = np.asarray(close, dtype=float)
    short = realized_vol(close, SHORT_VOL_WINDOW)
    long_ = realized_vol(close, LONG_VOL_WINDOW)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = short / long_
    out[~np.isfinite(out)] = np.nan
    return out


def align_market_data(cfg: MarketConfig, bars_by_symbol: dict[str, list[dict]]) -> RegimeMarketData:
    """把各标的日线对齐到共同交易日（交集，升序），构造 `RegimeMarketData`（纯函数）。

    结构沿用美股的 `RegimeMarketData`：`qqq_*` 字段装基准，`vix_close` 装波动比。
    """
    by_symbol: dict[str, dict[str, dict]] = {}
    for sym in cfg.symbols:
        rows = bars_by_symbol.get(sym) or []
        by_symbol[sym] = {r["time"]: r for r in rows if r.get("close") is not None}
        if not by_symbol[sym]:
            raise RuntimeError(f"缺少 {sym} 的行情，无法计算市场状态")
    common = set.intersection(*(set(v) for v in by_symbol.values()))
    if not common:
        raise RuntimeError("各标的无共同交易日，无法对齐")
    days = sorted(common)

    def close_vec(sym: str) -> np.ndarray:
        return np.array([by_symbol[sym][d]["close"] for d in days], dtype=float)

    def matrix(syms: tuple[str, ...]) -> np.ndarray:
        return np.column_stack([close_vec(s) for s in syms])

    bench = by_symbol[cfg.benchmark]
    bench_close = close_vec(cfg.benchmark)
    return RegimeMarketData(
        dates=[date.fromisoformat(d) for d in days],
        qqq_close=bench_close,
        qqq_high=np.array([bench[d]["high"] for d in days], dtype=float),
        qqq_low=np.array([bench[d]["low"] for d in days], dtype=float),
        qqq_volume=np.array([bench[d]["volume"] for d in days], dtype=float),
        vix_close=vol_ratio(bench_close),
        offense_prices=matrix(cfg.offense),
        defense_prices=matrix(cfg.defense),
        cash_prices=matrix(cfg.cash),
    )


def fetch_bars(cfg: MarketConfig, lookback_days: int) -> dict[str, list[dict]]:
    """逐只拉日线（同步入口，在子进程里调用；内部跑事件循环）。拉不到的标的给空列表，由对齐报错。"""
    from app.services.skills.kline import _fetch_yahoo

    end = date.today()
    start = (end - timedelta(days=lookback_days)).isoformat()

    async def _all() -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for sym in cfg.symbols:
            try:
                out[sym] = await _fetch_yahoo(sym, start, end.isoformat(), "1d")
            except Exception as e:  # noqa: BLE001
                logger.warning("regime_cnhk_fetch_failed", symbol=sym, error=str(e))
                out[sym] = []
            await asyncio.sleep(_FETCH_GAP_SECONDS)
        return out

    return asyncio.run(_all())


def compute_records(market: str, bars_by_symbol: dict[str, list[dict]]) -> list[RegimeDailyRecord]:
    """由日线算逐日状态记录（纯函数）。"""
    cfg = MARKET_CONFIGS[market]
    return compute_regime_from_market(align_market_data(cfg, bars_by_symbol))


def persist_records(session: Session, market: str, records: list[RegimeDailyRecord]) -> int:
    """按 (market, trade_date) upsert，返回写入 / 更新条数。"""
    existing = {
        r.trade_date: r
        for r in session.exec(select(RegimeMarketFeatures).where(RegimeMarketFeatures.market == market)).all()
    }
    written = 0
    for rec in records:
        row = existing.get(rec.trade_date)
        if row is None:
            row = RegimeMarketFeatures(market=market, trade_date=rec.trade_date)
            session.add(row)
        row.benchmark_return = rec.qqq_return
        row.realized_vol = rec.realized_vol
        row.vol_ratio = rec.vix
        row.ods = rec.ods
        row.cf = rec.cf
        row.obv_slope = rec.obv_slope
        row.cmf = rec.cmf
        row.p_risk_on = rec.p_risk_on
        row.p_neutral = rec.p_neutral
        row.p_risk_off = rec.p_risk_off
        row.regime_label = rec.regime_label
        row.confirmed_label = rec.confirmed_label
        row.params_version = rec.params_version
        written += 1
    session.commit()
    return written


def run_market_stage(session: Session, market: str, lookback_days: int = 2600) -> dict:
    """抓数 → 算状态 → 落库，返回摘要。

    回看约 7 年：A 股科创 50 / 港股恒生科技 ETF 都是 2020 年下半年上市，共同历史从那时算起，
    扣掉 60 日波动窗口与 252 日拟合门槛后约 2022 年起有状态。选篮子时也要避开 Yahoo 历史残缺的品种
    （如 2828.HK 只有约 600 根），否则会把整个市场的共同历史截短。
    """
    started = time.monotonic()
    cfg = MARKET_CONFIGS[market]
    records = compute_records(market, fetch_bars(cfg, lookback_days))
    written = persist_records(session, market, records)
    latest = next((r for r in reversed(records) if r.p_risk_on is not None), None)
    logger.info("regime_cnhk_stage_done", market=market, rows=len(records), written=written,
                latest_date=latest.trade_date if latest else None,
                latest_label=latest.confirmed_label if latest else None,
                seconds=round(time.monotonic() - started, 1))
    return {"market": market, "rows": len(records), "written": written,
            "latest_date": latest.trade_date if latest else None}
