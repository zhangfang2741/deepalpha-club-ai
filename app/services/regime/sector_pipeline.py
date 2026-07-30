"""行业（板块）级 regime 管线：每个板块独立跑 HMM，落库 regime_sector_features。"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlmodel import Session, select

from app.core.logging import logger
from app.models.regime_sector_features import RegimeSectorFeatures
from app.services.regime.constants import LABEL_RISK_OFF
from app.services.regime.engine import run_walk_forward
from app.services.regime.fetcher import SectorMarketData, fetch_sector_market_data
from app.services.regime.sector_features import (
    SECTOR_LABEL_WEIGHTS,
    build_sector_feature_series,
    stack_sector_features,
)


@dataclass
class SectorRegimeRecord:
    """单个板块单日待落库/展示的记录。"""

    trade_date: str
    sector: str
    sector_ret: float | None
    sector_vol: float | None
    vix: float | None
    rs_vs_market: float | None
    sector_cmf: float | None
    p_risk_on: float | None
    p_neutral: float | None
    p_risk_off: float | None
    regime_label: str | None
    confirmed_label: str | None
    params_version: str | None
    factor_weight: float | None


def _n(x: float) -> float | None:
    return None if (x is None or np.isnan(x)) else float(x)


def compute_sector_regimes(data: SectorMarketData) -> dict[str, list[SectorRegimeRecord]]:
    """对每个板块独立计算逐日 regime 记录（纯函数，无 IO）。"""
    out: dict[str, list[SectorRegimeRecord]] = {}
    for sector_key, bars in data.sectors.items():
        series = build_sector_feature_series(
            sector_close=bars["close"],
            sector_high=bars["high"],
            sector_low=bars["low"],
            sector_volume=bars["volume"],
            market_close=data.market_close,
            vix_close=data.vix_close,
        )
        feats = stack_sector_features(series)
        valid = np.asarray(~np.isnan(feats).any(axis=1), dtype=bool)
        result = run_walk_forward(
            data.dates, feats, valid, label_weights=SECTOR_LABEL_WEIGHTS
        )

        recs: list[SectorRegimeRecord] = []
        for i, dr in enumerate(result.daily):
            p_off = dr.posteriors.get(LABEL_RISK_OFF, float("nan"))
            fw = None if np.isnan(p_off) else float(1.0 - p_off)
            recs.append(
                SectorRegimeRecord(
                    trade_date=dr.date.isoformat(),
                    sector=sector_key,
                    sector_ret=_n(series["sector_ret"][i]),
                    sector_vol=_n(series["sector_vol"][i]),
                    vix=_n(series["vix"][i]),
                    rs_vs_market=_n(series["rs_vs_market"][i]),
                    sector_cmf=_n(series["sector_cmf"][i]),
                    p_risk_on=_n(dr.posteriors.get("risk_on", float("nan"))),
                    p_neutral=_n(dr.posteriors.get("neutral", float("nan"))),
                    p_risk_off=_n(p_off),
                    regime_label=dr.label or None,
                    confirmed_label=dr.confirmed_label,
                    params_version=dr.params_version,
                    factor_weight=fw,
                )
            )
        out[sector_key] = recs
    return out


def persist_sector_records(
    session: Session, by_sector: dict[str, list[SectorRegimeRecord]]
) -> int:
    """按 (trade_date, sector) upsert 到 regime_sector_features。"""
    existing = {
        (r.trade_date, r.sector): r
        for r in session.exec(select(RegimeSectorFeatures)).all()
    }
    written = 0
    for recs in by_sector.values():
        for rec in recs:
            row = existing.get((rec.trade_date, rec.sector))
            if row is None:
                row = RegimeSectorFeatures(trade_date=rec.trade_date, sector=rec.sector)
                session.add(row)
            row.sector_ret = rec.sector_ret
            row.sector_vol = rec.sector_vol
            row.vix = rec.vix
            row.rs_vs_market = rec.rs_vs_market
            row.sector_cmf = rec.sector_cmf
            row.p_risk_on = rec.p_risk_on
            row.p_neutral = rec.p_neutral
            row.p_risk_off = rec.p_risk_off
            row.regime_label = rec.regime_label
            row.confirmed_label = rec.confirmed_label
            row.params_version = rec.params_version
            row.factor_weight = rec.factor_weight
            written += 1
    session.commit()
    return written


def run_sector_regime_stage(session: Session, lookback_days: int = 1400) -> dict:
    """执行行业级 pipeline 阶段：抓数→逐板块算状态→落库，返回摘要。"""
    logger.info("regime_sector_stage_start", lookback_days=lookback_days)
    data = fetch_sector_market_data(lookback_days=lookback_days)
    by_sector = compute_sector_regimes(data)
    written = persist_sector_records(session, by_sector)
    latest = {
        key: (recs[-1].confirmed_label if recs else None)
        for key, recs in by_sector.items()
    }
    logger.info(
        "regime_sector_stage_done", sectors=len(by_sector), written=written
    )
    return {
        "sectors": len(by_sector),
        "written": written,
        "latest_labels": latest,
    }
