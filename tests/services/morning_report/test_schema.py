"""晨报内容 schema 校验：结构齐全性、双语非空、模块数量约束。"""

import pytest
from pydantic import ValidationError

from app.services.morning_report.schema import MorningReportContent


def _lt(zh: str = "中文", en: str = "English") -> dict:
    return {"zh": zh, "en": en}


def _entry() -> dict:
    return {
        "fact": _lt(),
        "insight": _lt(),
        "prediction": _lt("未来24-72小时…", "In the next 24-72h…"),
        "verification": _lt("盯 SOXX 期权偏度", "Watch SOXX skew"),
    }


def _section(key: str) -> dict:
    return {"key": key, "title": _lt(), "entries": [_entry()]}


def _valid_content() -> dict:
    return {
        "headline": _lt("美股正把降息落地重新定价为盈利放缓", "US is repricing cuts as earnings slowdown"),
        "summary": _lt("纳指跌入回调区间", "Nasdaq entered correction"),
        "metrics": [
            {"name": _lt("纳指100", "Nasdaq 100"), "value": "-1.2%", "direction": "down", "note": _lt("隔夜", "overnight")},
            {"name": _lt("VIX", "VIX"), "value": "18.4", "direction": "up", "note": _lt("+1.6", "+1.6")},
            {"name": _lt("美债10Y", "US 10Y"), "value": "4.21%", "direction": "down", "note": _lt("-3bp", "-3bp")},
        ],
        "sections": [
            _section("pricing_gap"),
            _section("earnings_valuation"),
            _section("industry_chain"),
            _section("crowding_risk"),
        ],
        "stocks": [
            {
                "symbol": "NVDA",
                "name": _lt("英伟达", "NVIDIA"),
                "change_pct": "-2.4%",
                "direction": "down",
                "bull": _lt("$210 GB300超预期", "$210 on GB300 beat"),
                "base": _lt("$185 指引中值", "$185 at guide midpoint"),
                "bear": _lt("$150 capex见顶", "$150 if capex peaks"),
            },
            {
                "symbol": "AAPL",
                "name": _lt("苹果", "Apple"),
                "change_pct": "+0.8%",
                "direction": "up",
                "bull": _lt("$260 服务收入超预期", "$260 on services beat"),
                "base": _lt("$230 硬件季节性平淡", "$230 on soft hardware seasonality"),
                "bear": _lt("$200 iPhone需求走弱", "$200 if iPhone demand softens"),
            },
        ],
        "catalysts": [
            {"date": "2026-09-12", "event": _lt("美国8月CPI", "US Aug CPI"), "why": _lt("决定9月降息幅度", "Sets Sept cut size"), "market": "us"},
            {"date": "2026-09-18", "event": _lt("FOMC议息", "FOMC"), "why": _lt("点阵图中枢", "Dot plot"), "market": "us"},
            {"date": "2026-09-22", "event": _lt("LPR报价", "LPR fix"), "why": _lt("五年期是否下调", "5Y cut or not"), "market": "cn"},
        ],
    }


def test_valid_content_passes():
    content = MorningReportContent.model_validate(_valid_content())
    assert content.metrics[0].direction == "down"
    assert content.sections[3].key == "crowding_risk"
    assert content.stocks[0].symbol == "NVDA"


def test_missing_section_key_rejected():
    """四个模块 key 必须齐全（少一个都非法）。"""
    data = _valid_content()
    data["sections"] = data["sections"][:3]
    with pytest.raises(ValidationError, match="crowding_risk"):
        MorningReportContent.model_validate(data)


def test_localized_text_empty_rejected():
    """双语字段空串非法——保证英文版不会悄悄缺内容。"""
    data = _valid_content()
    data["headline"]["en"] = ""
    with pytest.raises(ValidationError):
        MorningReportContent.model_validate(data)


def test_metrics_must_be_three():
    data = _valid_content()
    data["metrics"] = data["metrics"][:2]
    with pytest.raises(ValidationError):
        MorningReportContent.model_validate(data)


def test_duplicate_section_rejected():
    data = _valid_content()
    data["sections"][1] = _section("pricing_gap")
    with pytest.raises(ValidationError, match="重复"):
        MorningReportContent.model_validate(data)
