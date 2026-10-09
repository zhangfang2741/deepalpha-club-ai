"""把 regime 因子表（大盘 / 行业）读成宏观格、行业格要的样子。

纯函数（build_state / sector_rows / strongest_weakest）与 DB 读取（load_*，同步，调用方放线程池）分开，
前者单测覆盖。大盘状态：美股读 regime_features，A 股 / 港股读 regime_market_features（带 market 列）；行业状态：美股读 regime_sector_features，A 股 / 港股读 regime_market_sector_features（行业 = 申万 / 恒生一级，key 即中文名）。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import col, select

from app.models.regime_features import RegimeFeatures
from app.models.regime_sector_features import RegimeSectorFeatures
from app.schemas.macro import MacroStateInputsOut, MacroStateOut, MacroStatePoint, SectorBriefOut, SectorRowOut
from app.services.regime.constants import LABEL_ZH, SECTOR_CHILDREN, SECTOR_NAME_ZH, SECTOR_SYMBOL

LABEL_EN = {"risk_on": "Risk-on", "neutral": "Neutral", "risk_off": "Risk-off"}

SECTOR_NAME_EN: dict[str, str] = {
    "technology": "Technology", "discretionary": "Discretionary",
    "communication": "Communication", "financials": "Financials", "industrials": "Industrials",
    "energy": "Energy", "materials": "Materials", "healthcare": "Health Care", "staples": "Staples",
    "utilities": "Utilities", "realestate": "Real Estate",
    "tech_software": "Software", "tech_cyber": "Cybersecurity", "tech_cloud": "Cloud",
    "tech_semis": "Semiconductors", "disc_retail": "Retail", "disc_homebuild": "Homebuilders",
    "disc_leisure": "Leisure", "comm_social": "Social Media", "comm_gaming": "Gaming",
    "comm_internet": "Internet", "fin_banks": "Banks", "fin_regional": "Regional Banks",
    "fin_insurance": "Insurance", "fin_brokers": "Brokers", "ind_defense": "Aerospace & Defense",
    "ind_transport": "Transportation", "energy_ep": "Oil & Gas E&P", "energy_services": "Oil Services",
    "energy_clean": "Clean Energy", "mat_metals": "Metals & Mining", "mat_gold": "Gold Miners",
    "mat_lithium": "Lithium", "hc_biotech": "Biotech", "hc_devices": "Medical Devices",
    "hc_pharma": "Pharma", "re_residential": "Residential REIT", "re_mortgage": "Mortgage REIT",
}


def sector_name(key: str, lang: str) -> str:
    """行业展示名。"""
    if lang == "en":
        from app.services.quant_research.cnhk.sectors import NATIVE_SECTOR_EN

        return SECTOR_NAME_EN.get(key) or NATIVE_SECTOR_EN.get(key, key)
    return SECTOR_NAME_ZH.get(key, key)


def label_text(label: str, lang: str) -> str:
    """状态展示名。"""
    return (LABEL_EN if lang == "en" else LABEL_ZH).get(label, label)


@dataclass(frozen=True)
class StateRow:
    """大盘状态表的一行（只取宏观格需要的字段）。"""
    trade_date: str
    confirmed_label: str | None
    regime_label: str | None
    p_risk_on: float | None
    p_neutral: float | None
    p_risk_off: float | None
    # 当天的模型原料（旧调用方 / 测试可不传）
    ret: float | None = None
    vol: float | None = None
    vix: float | None = None
    vol_ratio: float | None = None
    ods: float | None = None
    cf: float | None = None


@dataclass(frozen=True)
class SectorRow:
    """行业状态表的一行（只取行业格需要的字段）。"""
    trade_date: str
    sector: str
    rs_vs_market: float | None
    confirmed_label: str | None
    regime_label: str | None
    p_risk_on: float | None


def _label(r: StateRow) -> str | None:
    return r.confirmed_label or r.regime_label


def build_state(rows: list[StateRow], lang: str = "zh") -> MacroStateOut | None:
    """rows 按日期升序。取最后一个有后验的交易日。"""
    valid = [r for r in rows if _label(r) and r.p_risk_on is not None]
    if not valid:
        return None
    last = valid[-1]
    label = _label(last)
    assert label is not None
    probs = {"risk_on": last.p_risk_on or 0.0, "neutral": last.p_neutral or 0.0,
             "risk_off": last.p_risk_off or 0.0}
    days = 0
    for r in reversed(valid):
        if _label(r) != label:
            break
        days += 1
    return MacroStateOut(
        label=label, label_text=label_text(label, lang), probability=round(probs.get(label, 0.0), 3),
        p_risk_on=round(probs["risk_on"], 3), p_neutral=round(probs["neutral"], 3),
        p_risk_off=round(probs["risk_off"], 3), days_in_state=days, as_of=last.trade_date,
        inputs=_inputs(last),
    )


def _inputs(r: StateRow) -> MacroStateInputsOut | None:
    vals = (r.ret, r.vol, r.vix, r.vol_ratio, r.ods, r.cf)
    if all(v is None for v in vals):
        return None
    def rd(v: float | None, n: int) -> float | None:
        return None if v is None else round(v, n)
    return MacroStateInputsOut(ret=rd(r.ret, 4), vol=rd(r.vol, 4), vix=rd(r.vix, 2),
                               vol_ratio=rd(r.vol_ratio, 2), ods=rd(r.ods, 4), cf=rd(r.cf, 4))


def state_history(rows: list[StateRow]) -> list[MacroStatePoint]:
    """近一年状态色带。

    中间尚未确认的天数留空（状态切换期）；但末尾连续未确认的天数用当日原始判定补上并标 pending，
    否则最新一天会是灰的，与上方「市场状态」卡片（确认标签缺失时用原始标签）对不上。
    """
    points = [MacroStatePoint(date=r.trade_date, label=r.confirmed_label) for r in rows]
    for i in range(len(rows) - 1, -1, -1):
        if rows[i].confirmed_label is not None:
            break
        if rows[i].regime_label is not None:
            points[i] = MacroStatePoint(date=rows[i].trade_date, label=rows[i].regime_label, pending=True)
    return points


def sector_rows(rows: list[SectorRow], counts: dict[str, dict[str, int]], lang: str = "zh") -> list[SectorRowOut]:
    """按相对强弱从强到弱；没有强弱数据的垫底。"""
    out = [
        SectorRowOut(
            key=r.sector, name=sector_name(r.sector, lang), rs_vs_market=r.rs_vs_market,
            label=r.confirmed_label or r.regime_label, p_risk_on=r.p_risk_on,
            # 有细分 ETF 的一级行业可下钻看子行业强弱（只看、不筛雷达；雷达行业仍是 GICS 一级）
            has_children=bool(SECTOR_CHILDREN.get(r.sector)),
            buy_count=counts.get(r.sector, {}).get("buy", 0), sell_count=counts.get(r.sector, {}).get("sell", 0),
        )
        for r in rows
    ]
    out.sort(key=lambda s: (s.rs_vs_market is None, -(s.rs_vs_market or 0.0)))
    return out


def strongest_weakest(rows: list[SectorRow], lang: str = "zh") -> tuple[SectorBriefOut | None, SectorBriefOut | None]:
    """相对强弱最强、最弱的各一个行业。"""
    ranked = [r for r in rows if r.rs_vs_market is not None]
    if not ranked:
        return None, None
    ranked.sort(key=lambda r: r.rs_vs_market or 0.0, reverse=True)

    def brief(r: SectorRow) -> SectorBriefOut:
        return SectorBriefOut(key=r.sector, name=sector_name(r.sector, lang), rs_vs_market=r.rs_vs_market,
                              label=r.confirmed_label or r.regime_label)

    return brief(ranked[0]), (brief(ranked[-1]) if len(ranked) > 1 else None)


# ---- DB 读取（同步） ----

def load_state_rows(limit: int = 260, market: str = "us") -> list[StateRow]:
    """读最近 limit 个交易日的大盘状态（升序）。美股读 regime_features，A 股 / 港股读 regime_market_features。"""
    from app.db.session import get_sync_session_cm
    from app.models.regime_market_features import RegimeMarketFeatures

    with get_sync_session_cm() as session:
        if market == "us":
            rows = session.exec(
                select(RegimeFeatures).order_by(col(RegimeFeatures.trade_date).desc()).limit(limit)
            ).all()
        else:
            rows = session.exec(
                select(RegimeMarketFeatures).where(RegimeMarketFeatures.market == market)
                .order_by(col(RegimeMarketFeatures.trade_date).desc()).limit(limit)
            ).all()
    out = [
        StateRow(r.trade_date, r.confirmed_label, r.regime_label, r.p_risk_on, r.p_neutral, r.p_risk_off,
                 ret=getattr(r, "qqq_return", None) if market == "us" else getattr(r, "benchmark_return", None),
                 vol=r.realized_vol,
                 vix=getattr(r, "vix", None) if market == "us" else None,
                 vol_ratio=None if market == "us" else getattr(r, "vol_ratio", None),
                 ods=r.ods, cf=r.cf)
        for r in rows
    ]
    out.sort(key=lambda r: r.trade_date)
    return out


def load_sector_rows(parent: str | None = None, as_of: str | None = None) -> list[SectorRow]:
    """最新一个交易日（as_of 给定时取不晚于它的最近交易日）的一级行业（parent=None）或某一级行业下的子行业。"""
    from app.db.session import get_sync_session_cm

    cond = col(RegimeSectorFeatures.parent).is_(None) if parent is None else RegimeSectorFeatures.parent == parent
    day_q = select(RegimeSectorFeatures.trade_date).where(cond)
    if as_of is not None:
        day_q = day_q.where(RegimeSectorFeatures.trade_date <= as_of)
    with get_sync_session_cm() as session:
        latest = session.exec(day_q.order_by(col(RegimeSectorFeatures.trade_date).desc()).limit(1)).first()
        if latest is None:
            return []
        rows = session.exec(
            select(RegimeSectorFeatures).where(RegimeSectorFeatures.trade_date == latest, cond)
        ).all()
    return [SectorRow(r.trade_date, r.sector, r.rs_vs_market, r.confirmed_label, r.regime_label, r.p_risk_on)
            for r in rows if parent is not None or r.sector in SECTOR_SYMBOL]  # 丢掉已下线的旧一级行业行（如半导体）


def load_market_sector_rows(market: str, as_of: str | None = None) -> list[SectorRow]:
    """A 股 / 港股：最新一个交易日（as_of 给定时取不晚于它的最近交易日）的行业状态（申万 / 恒生一级，key 即行业名）。"""
    from app.db.session import get_sync_session_cm
    from app.models.regime_market_sector_features import RegimeMarketSectorFeatures as M

    day_q = select(M.trade_date).where(M.market == market)
    if as_of is not None:
        day_q = day_q.where(M.trade_date <= as_of)
    with get_sync_session_cm() as session:
        latest = session.exec(day_q.order_by(col(M.trade_date).desc()).limit(1)).first()
        if latest is None:
            return []
        rows = session.exec(select(M).where(M.market == market, M.trade_date == latest)).all()
    return [SectorRow(r.trade_date, r.sector, r.rs_vs_market, r.confirmed_label, r.regime_label, r.p_risk_on)
            for r in rows]
