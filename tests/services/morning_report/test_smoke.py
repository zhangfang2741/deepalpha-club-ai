"""真实 LLM 冒烟：生成一份完整美股晨报并通过 schema。上线前手动跑。"""

import pytest

from app.services.morning_report.generator import generate_report


@pytest.mark.slow
@pytest.mark.asyncio
async def test_generate_full_us_report():
    content, meta = await generate_report("us", "2026-09-08")
    assert content.metrics[0].value
    assert {s.key for s in content.sections} == {
        "pricing_gap", "earnings_valuation", "industry_chain", "crowding_risk"
    }
    assert content.summary.zh and content.summary.en
    assert meta["duration_ms"] > 0
