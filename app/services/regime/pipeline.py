"""regime pipeline 新阶段：`run_regime_stage`。

「算一次，双消费」：
1. 拉行情 → 算信号（三篮子 ODS/CF + 量价 OBV/CMF + 波动/VIX/纳指收益）；
2. 走-前向 HMM（月末冻结、只用历史、滤波后验、状态不回改）产出逐利/观望/避险后验；
3. 落库 `regime_features`（因子表）：既给面板消费，又把 p_避险 → factor_weight 供下游因子加权。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlmodel import Session, select

from app.core.logging import logger
from app.models.regime_features import RegimeFeatures
from app.services.regime.constants import (
    LABEL_RISK_OFF,
    OBV_CMF_WINDOW,
)
from app.services.regime.engine import run_walk_forward
from app.services.regime.features import build_feature_series, stack_features
from app.services.regime.fetcher import RegimeMarketData, fetch_regime_market_data
from app.services.regime.indicators import cmf, obv_slope


@dataclass
class RegimeDailyRecord:
    """单日待落库/展示的完整记录。"""

    trade_date: str
    qqq_return: float | None
    realized_vol: float | None
    vix: float | None
    ods: float | None
    cf: float | None
    obv_slope: float | None
    cmf: float | None
    p_risk_on: float | None
    p_neutral: float | None
    p_risk_off: float | None
    regime_label: str | None
    confirmed_label: str | None
    params_version: str | None
    factor_weight: float | None


def _nan_to_none(x: float) -> float | None:
    return None if (x is None or np.isnan(x)) else float(x)


def compute_regime_from_market(data: RegimeMarketData) -> list[RegimeDailyRecord]:
    """由对齐行情计算逐日 regime 记录（纯函数，无 IO，便于测试）。"""
    series = build_feature_series(
        qqq_close=data.qqq_close,
        vix_close=data.vix_close,
        offense_prices=data.offense_prices,
        defense_prices=data.defense_prices,
        cash_prices=data.cash_prices,
    )
    feats = stack_features(series)
    valid_mask = np.asarray(~np.isnan(feats).any(axis=1), dtype=bool)

    result = run_walk_forward(data.dates, feats, valid_mask)

    # 量价确认（真实 OBV 斜率 / CMF），用纳指量价
    obv_s = obv_slope(data.qqq_close, data.qqq_volume, OBV_CMF_WINDOW)
    cmf_v = cmf(
        data.qqq_high, data.qqq_low, data.qqq_close, data.qqq_volume, OBV_CMF_WINDOW
    )

    records: list[RegimeDailyRecord] = []
    for i, dr in enumerate(result.daily):
        p_off = dr.posteriors.get(LABEL_RISK_OFF, float("nan"))
        factor_weight = None if np.isnan(p_off) else float(1.0 - p_off)
        records.append(
            RegimeDailyRecord(
                trade_date=dr.date.isoformat(),
                qqq_return=_nan_to_none(series["qqq_ret"][i]),
                realized_vol=_nan_to_none(series["realized_vol"][i]),
                vix=_nan_to_none(series["vix"][i]),
                ods=_nan_to_none(series["ods"][i]),
                cf=_nan_to_none(series["cf"][i]),
                obv_slope=_nan_to_none(obv_s[i]),
                cmf=_nan_to_none(cmf_v[i]),
                p_risk_on=_nan_to_none(dr.posteriors.get("risk_on", float("nan"))),
                p_neutral=_nan_to_none(dr.posteriors.get("neutral", float("nan"))),
                p_risk_off=_nan_to_none(p_off),
                regime_label=dr.label or None,
                confirmed_label=dr.confirmed_label,
                params_version=dr.params_version,
                factor_weight=factor_weight,
            )
        )
    return records


def persist_records(session: Session, records: list[RegimeDailyRecord]) -> int:
    """按 trade_date upsert 到 regime_features，返回写入/更新条数。"""
    existing = {
        r.trade_date: r
        for r in session.exec(select(RegimeFeatures)).all()
    }
    written = 0
    for rec in records:
        row = existing.get(rec.trade_date)
        if row is None:
            row = RegimeFeatures(trade_date=rec.trade_date)
            session.add(row)
        row.qqq_return = rec.qqq_return
        row.realized_vol = rec.realized_vol
        row.vix = rec.vix
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
        row.factor_weight = rec.factor_weight
        written += 1
    session.commit()
    return written


def run_regime_stage(session: Session, lookback_days: int = 1400) -> dict:
    """执行 pipeline 阶段：抓数→算状态→落库，返回运行摘要。"""
    logger.info("regime_stage_start", lookback_days=lookback_days)
    data = fetch_regime_market_data(lookback_days=lookback_days)
    records = compute_regime_from_market(data)
    written = persist_records(session, records)
    latest = records[-1] if records else None
    logger.info(
        "regime_stage_done",
        rows=len(records),
        written=written,
        latest_date=latest.trade_date if latest else None,
        latest_label=latest.confirmed_label if latest else None,
    )
    return {
        "rows": len(records),
        "written": written,
        "latest_date": latest.trade_date if latest else None,
        "latest_label": latest.confirmed_label if latest else None,
        "latest_factor_weight": latest.factor_weight if latest else None,
    }
