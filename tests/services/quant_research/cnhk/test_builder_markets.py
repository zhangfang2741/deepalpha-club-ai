"""三个市场同一条评分管线：A 股 / 港股不显示没有数据源的指标，文案按市场称呼样本，港股带汇率说明。"""

import json
from datetime import date
from pathlib import Path

from app.services.quant_research import copy as tx
from app.services.quant_research.builder import build_payload, evaluate, finalize_overall
from app.services.quant_research.cnhk import hk_source
from app.services.quant_research.cnhk.pipeline import build_cnhk_inputs
from app.services.quant_research.markets import PROFILES, normalize_symbol, profile
from app.services.quant_research.metrics import METRICS
from app.services.quant_research.scoring import OverallScore

FIX = Path(__file__).resolve().parents[3] / "fixtures" / "quant_research" / "cnhk"


def _hk_inputs():
    d = json.loads((FIX / "hk_00700.json").read_text())
    reps = hk_source.hk_reports(d["INCOME"], d["CASHFLOW"], d["report_list"], "12-31", financial=False)
    bal = hk_source.hk_balance(d["BALANCE"], financial=False)
    prices = [{"date": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", "price": 400.0 + i * 0.1} for i in range(300)]
    est = [{"date": "2026-12-31", "epsAvg": 25.5, "epsLow": 23.0, "epsHigh": 29.8, "revenueAvg": None,
            "numAnalystsEps": 17}, {"date": "2027-12-31", "epsAvg": 27.3, "numAnalystsEps": 17}]
    return build_cnhk_inputs(market="hk", symbol="00700", name="腾讯控股", sector="communication_services",
                             as_of=date(2026, 10, 2), reports=reps, balance=bal, estimates=est, prices=prices,
                             shares=9.09e9, amount_scale=1 / 0.8544, estimate_scale=1 / 0.8544,
                             fx={"hkd_cny": 0.8544, "estimate_currency": "CNY"})


def test_unsupported_metrics_are_hidden_per_market():
    ev = evaluate(_hk_inputs(), [], {})
    keys = {s.key for d in ev.dims for s in d.metrics}
    assert keys.isdisjoint(PROFILES["hk"].unsupported)
    assert keys == set(METRICS) - PROFILES["hk"].unsupported
    assert PROFILES["us"].unsupported == frozenset()


def test_payload_uses_market_universe_and_currency_note():
    ev = evaluate(_hk_inputs(), [], {})
    finalize_overall(ev, [])
    zh = build_payload(ev, "zh", in_universe=False, sector_sample=38)
    assert zh.market == "hk" and zh.peer_group.universe_name == "港股通及大中型港股"
    assert "不在港股通及大中型港股样本内" in zh.peer_group.text
    assert zh.as_of.currency_note.startswith("财务数据按 1 人民币 = 1.1704 港元")
    assert zh.as_of.fiscal_period == "FY26 H1"
    en = build_payload(ev, "en", in_universe=True, sector_sample=38)
    assert en.as_of.currency_note.startswith("Financials converted to HKD")
    texts = [zh.peer_group.text, zh.as_of.currency_note, en.as_of.currency_note]
    assert all(tx.contains_forbidden(t) == [] for t in texts)


def test_overall_text_names_market_sample():
    o = OverallScore(score=70.0, universe_percentile=91.0, grade="A", dimensions_used=4)
    assert tx.overall_text(o, "zh", "cn") == "综合分 70.0 · A 股市值前 1800 前 9%"
    assert tx.overall_text(o, "zh") == "综合分 70.0 · 标普1500 前 9%"
    assert tx.currency_note({"hkd_cny": 0.85, "estimate_currency": "USD"}, "zh").endswith("分析师预期原为 USD，按当日汇率折算")
    assert tx.currency_note(None, "zh") is None


def test_profiles_and_symbols():
    assert profile("cn").has_moat is False and profile("us").has_moat is True
    assert normalize_symbol("hk", "700") == "00700" and normalize_symbol("cn", "1") == "000001"
