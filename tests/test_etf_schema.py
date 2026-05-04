"""ETF schema 验证测试。"""
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.etf import ETFSummary, FlowDataPoint


def test_flow_data_point_fields_are_correct():
    point = FlowDataPoint(
        symbol="SPY",
        date=date(2026, 4, 30),
        close=402.5,
        volume=52_000_000,
        dollar_volume=20_930_000_000.0,
        return_pct=0.62,
    )
    assert point.symbol == "SPY"
    assert point.close == 402.5
    assert point.dollar_volume == 20_930_000_000.0


def test_flow_data_point_rejects_negative_volume():
    with pytest.raises(ValidationError):
        FlowDataPoint(
            symbol="SPY",
            date=date(2026, 4, 30),
            close=402.5,
            volume=-1,
            dollar_volume=0.0,
            return_pct=0.0,
        )


def test_etf_summary_fields_are_correct():
    summary = ETFSummary(
        symbol="QQQ",
        name="Invesco QQQ Trust",
        category="Equity",
        current_price=480.0,
        price_change_pct=1.25,
        period_dollar_volume=50_000_000_000.0,
    )
    assert summary.symbol == "QQQ"
    assert summary.category == "Equity"
    assert summary.period_dollar_volume == 50_000_000_000.0
