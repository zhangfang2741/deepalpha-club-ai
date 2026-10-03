"""A 股 / 港股取数归一化、经济通解析、一致预期组装（真实响应摘取的夹具，2026-10-03）。"""

import json
from datetime import date
from pathlib import Path

import pytest

from app.services.quant_research.cnhk import cn_source, etnet, hk_source
from app.services.quant_research.cnhk.pipeline import (
    build_cnhk_inputs,
    cn_estimates,
    fiscal_date,
    hk_estimates,
    scale_estimates,
)
from app.services.quant_research.cnhk.reports import to_quarters
from app.services.quant_research.inputs import fiscal_year_actual, ttm
from app.services.quant_research.metrics import compute_metrics

FIX = Path(__file__).resolve().parents[3] / "fixtures" / "quant_research" / "cnhk"


def _hk(code: str) -> dict:
    return json.loads((FIX / f"hk_{code}.json").read_text())


# ---------- A 股 ----------

_G_INCOME = {"SECURITY_CODE": "600519", "SECURITY_NAME_ABBR": "贵州茅台", "REPORT_DATE": "2026-06-30 00:00:00",
             "NOTICE_DATE": "2026-08-15 00:00:00", "ORG_TYPE": "通用", "TOTAL_OPERATE_INCOME": 100.0,
             "OPERATE_INCOME": 98.0, "OPERATE_COST": 10.0, "TOTAL_PROFIT": 60.0, "INCOME_TAX": 15.0,
             "PARENT_NETPROFIT": 44.0, "BASIC_EPS": 35.6, "DILUTED_EPS": 35.5, "FE_INTEREST_EXPENSE": 2.0,
             "FINANCE_EXPENSE": -1.0}
_G_CASH = {"SECURITY_CODE": "600519", "REPORT_DATE": "2026-06-30 00:00:00", "NETCASH_OPERATE": 70.0,
           "NETCASH_INVEST": 25.0, "NETCASH_FINANCE": -38.0, "CONSTRUCT_LONG_ASSET": 8.0, "FA_IR_DEPR": 1.5,
           "IA_AMORTIZE": 0.5, "USERIGHT_ASSET_AMORTIZE": None}


def test_cn_report_general_company():
    r = cn_source.cn_report("G", _G_INCOME, _G_CASH)
    assert r["revenue"] == 100.0 and r["gross"] == 98.0 - 10.0
    assert r["ebit"] == 60.0 + 2.0          # 利润总额 + 利息费用
    assert r["da"] == 2.0 and r["capex"] == -8.0 and r["eps"] == 35.5
    assert r["report_date"] == "2026-06-30" and r["notice_date"] == "2026-08-15"


def test_cn_report_bank_has_no_gross_or_ebit():
    row = {**_G_INCOME, "ORG_TYPE": "银行", "TOTAL_OPERATE_INCOME": None, "OPERATE_COST": None,
           "FE_INTEREST_EXPENSE": None, "FINANCE_EXPENSE": None}
    r = cn_source.cn_report("B", row, None)
    assert r["revenue"] == 98.0 and r["gross"] is None and r["ebit"] is None and r["da"] is None


def test_cn_balance_general_vs_financial():
    row = {"REPORT_DATE": "2026-06-30", "TOTAL_ASSETS": 300.0, "TOTAL_PARENT_EQUITY": 250.0, "TOTAL_EQUITY": 260.0,
           "MONETARYFUNDS": 50.0, "TRADE_FINASSET": 3.0, "TRADE_FINASSET_NOTFVTPL": None, "SHORT_LOAN": None,
           "LONG_LOAN": None, "LEASE_LIAB": 0.2}
    g = cn_source.cn_balance("G", row)
    assert g["totalStockholdersEquity"] == 250.0 and g["cashAndShortTermInvestments"] == 53.0
    assert g["totalDebt"] == pytest.approx(0.2)
    b = cn_source.cn_balance("B", row)
    assert b["totalDebt"] is None and b["cashAndShortTermInvestments"] is None


def test_assemble_uses_org_type_and_dedupes():
    bank = {**_G_INCOME, "SECURITY_CODE": "601398", "ORG_TYPE": "银行"}
    older = {**_G_INCOME, "NOTICE_DATE": "2026-08-01 00:00:00", "PARENT_NETPROFIT": 1.0}
    out = cn_source.assemble([_G_INCOME, older, bank], [_G_CASH], [])
    assert out["600519"]["kind"] == "G" and out["601398"]["kind"] == "B"
    assert len(out["600519"]["reports"]) == 1 and out["600519"]["reports"][0]["net"] == 44.0  # 取披露日最新的一行


def test_periods():
    assert cn_source.quarter_ends(date(2022, 6, 30), date(2023, 1, 5)) == [
        date(2022, 6, 30), date(2022, 9, 30), date(2022, 12, 31)]
    # 10 月初：三季报（9/30）、中报（6/30）仍在披露窗口内，年报（去年 12/31）已超过 125 天
    assert cn_source.open_periods(date(2026, 10, 3)) == [date(2026, 6, 30), date(2026, 9, 30)]
    # 4 月中：年报与一季报都可能还没披露完
    assert cn_source.open_periods(date(2026, 4, 15)) == [date(2025, 12, 31), date(2026, 3, 31)]


def test_pick_universe_excludes_st_and_unmapped():
    meta = {
        "000001": cn_source.CnMeta("000001", "平安银行", "银行Ⅱ", "financials", 1e10, 2e11, "2026-09-30"),
        "000002": cn_source.CnMeta("000002", "*ST 某某", "电力", "utilities", 1e9, 9e11, "2026-09-30"),
        "000003": cn_source.CnMeta("000003", "某某", "未知行业", None, 1e9, 8e11, "2026-09-30"),
    }
    assert cn_source.pick_universe(meta) == ["000001"]


def test_cn_estimates_from_f10_fixture():
    f10 = json.loads((FIX / "f10_600519.json").read_text())
    est = cn_estimates(f10)
    assert [e["date"] for e in est] == ["2026-12-31", "2027-12-31", "2028-12-31"]
    e26 = est[0]
    assert e26["epsAvg"] == pytest.approx(67.249318, rel=1e-4) and e26["numAnalystsEps"] > 3
    assert e26["epsLow"] <= e26["epsAvg"] <= e26["epsHigh"] and e26["revenueAvg"] > 1e11


# ---------- 港股 ----------

def test_hk_tencent_reports_and_ttm():
    d = _hk("00700")
    reps = hk_source.hk_reports(d["INCOME"], d["CASHFLOW"], d["report_list"], "12-31", financial=False)
    assert reps[0]["report_date"] == "2026-06-30" and reps[0]["currency"] == "人民币"
    inc, cash = to_quarters(reps)
    # 营收取「营业额」（不含其他营业收入；「营运收入」是两者之和 7518 亿）：腾讯 2025 年 7437 亿元人民币
    assert fiscal_year_actual(inc, "revenue")[1] == pytest.approx(7.43689e11, rel=1e-3)
    assert ttm(inc, "revenue") > ttm(inc, "revenue", 4) > 0
    assert ttm(cash, "capitalExpenditure") < 0  # 购建固定资产在东财记正数，归一化为负
    bal = hk_source.hk_balance(d["BALANCE"], financial=False)
    assert bal["totalDebt"] > 0 and bal["cashAndShortTermInvestments"] > 0


def test_hk_bank_balance_has_no_debt():
    d = _hk("00005")
    reps = hk_source.hk_reports(d["INCOME"], d["CASHFLOW"], d["report_list"], "12-31", financial=True)
    assert all(r["ebit"] is None and r["gross"] is None for r in reps)
    assert reps[0]["currency"] == "美元"  # 原始申报币种；金额已被折成人民币
    assert hk_source.hk_balance(d["BALANCE"], financial=True)["totalDebt"] is None


def test_hk_march_fiscal_year():
    d = _hk("09988")
    reps = hk_source.hk_reports(d["INCOME"], d["CASHFLOW"], d["report_list"], "03-31", financial=False)
    inc, _ = to_quarters(reps)
    assert inc[0]["date"] == "2026-06-30" and inc[0]["fiscalYear"] == "2027" and inc[0]["period"] == "Q1"


def test_hk_universe_rules():
    def m(code, connect, cap, sector="industrials", shares=1e9):
        return hk_source.HkMeta(code, code, "工业工程", sector, "12-31", "一般企业", shares, cap, "2026-06-30", connect)
    meta = {"00001": m("00001", True, 1e8), "00002": m("00002", False, 3e9), "00003": m("00003", False, 1e9),
            "80700": m("80700", True, 3e12), "00004": m("00004", True, 5e9, sector=None)}
    assert hk_source.pick_universe(meta) == ["00001", "00002"]


@pytest.mark.parametrize(("code", "currency", "first_eps"), [
    ("00005", "USD", 1.64), ("00700", "CNY", 29.3), ("09988", "CNY", 6.155), ("01729", "HKD", 0.9)])
def test_etnet_parse(code, currency, first_eps):
    fc = etnet.parse((FIX / f"etnet_{code}.html").read_text())
    assert fc is not None and fc.currency == currency
    first = fc.rows[0]
    assert first.eps == pytest.approx(first_eps) and first.rating and first.target_hkd and first.updated


def test_etnet_unit_missing_uses_fallback_currency():
    fc = etnet.parse((FIX / "etnet_01913.html").read_text(), "EUR")  # 表头单位为空
    assert fc is not None and fc.currency == "EUR" and fc.rows[0].eps == pytest.approx(0.32)
    assert etnet.parse((FIX / "etnet_01913.html").read_text()).currency is None


def test_hk_estimates_freshness_and_fiscal_dates():
    fc = etnet.parse((FIX / "etnet_09988.html").read_text())
    est = hk_estimates(fc, "03-31", date(2026, 10, 3))
    assert [e["date"] for e in est][:2] == ["2027-03-31", "2028-03-31"]
    stale = hk_estimates(fc, "03-31", date(2027, 9, 1))  # 一年后再看：半年内没更新的券商都不算
    assert sum(e["numAnalystsEps"] for e in stale) < sum(e["numAnalystsEps"] for e in est)
    assert fiscal_date(2028, "02-28") == "2028-02-29" and fiscal_date(2027, "02-28") == "2027-02-28"
    assert scale_estimates([{"epsAvg": 2.0, "numAnalystsEps": 5}], 1.5) == [{"epsAvg": 3.0, "numAnalystsEps": 5}]


def test_build_inputs_scales_to_hkd_and_marks_bank_metrics():
    d = _hk("00005")
    reps = hk_source.hk_reports(d["INCOME"], d["CASHFLOW"], d["report_list"], "12-31", financial=True)
    bal = hk_source.hk_balance(d["BALANCE"], financial=True)
    prices = [{"date": f"2026-0{1 + i // 31}-{1 + i % 28:02d}", "price": 100.0 + i} for i in range(300)]
    inp = build_cnhk_inputs(market="hk", symbol="00005", name="汇丰控股", sector="financials", as_of=date(2026, 10, 2),
                            reports=reps, balance=bal, estimates=[], prices=prices, shares=1.7e10,
                            amount_scale=1 / 0.85, fx={"hkd_cny": 0.85, "estimate_currency": "USD"})
    raw_inc, _ = to_quarters(reps)
    assert ttm(inp.quarters_income, "revenue") == pytest.approx(ttm(raw_inc, "revenue") / 0.85)
    assert inp.market == "hk" and inp.shares_diluted == 1.7e10
    m = compute_metrics(inp)
    assert m["ev_ebitda_ttm"].status == "not_applicable" and m["ev_ebitda_ttm"].meta["reason"] == "financials_structure"
    assert m["pe_ttm"].status == "ok" and m["pb"].status == "ok"
