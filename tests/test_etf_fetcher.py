"""ETF fetcher 单元测试（mock httpx，不发真实网络请求）。"""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services.etf.fetcher import (
    TRACKED_ETFS,
    fetch_etf_flows,
    fetch_etf_list_summary,
)


def _make_fmp_response(closes: list, volumes: list) -> dict:
    """closes/volumes 按升序（最旧在前）传入，返回 FMP 格式响应（historical 降序）。"""
    base_date = date(2026, 4, 28)
    records = [
        {"date": (base_date + timedelta(days=i)).isoformat(), "close": c, "volume": v}
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]
    return {"symbol": "SPY", "historical": list(reversed(records))}


def _mock_httpx_get(payload: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = payload
    return mock_resp


def test_fetch_etf_flows_returns_flow_data_points():
    payload = _make_fmp_response([400.0, 402.0, 401.0], [50_000_000, 55_000_000, 48_000_000])
    with patch("app.services.etf.fetcher.httpx.get", return_value=_mock_httpx_get(payload)):
        result = fetch_etf_flows("SPY", "1mo")

    assert len(result) == 3
    assert result[0].symbol == "SPY"
    assert result[0].close == 400.0
    assert result[0].volume == 50_000_000
    assert result[0].dollar_volume == pytest.approx(400.0 * 50_000_000)


def test_fetch_etf_flows_calculates_return_pct():
    payload = _make_fmp_response([400.0, 402.0, 398.0], [50_000_000, 55_000_000, 48_000_000])
    with patch("app.services.etf.fetcher.httpx.get", return_value=_mock_httpx_get(payload)):
        result = fetch_etf_flows("SPY", "1mo")

    # 第一行无前日，return_pct = 0
    assert result[0].return_pct == 0.0
    # 第二行：(402 - 400) / 400 * 100 = 0.5
    assert result[1].return_pct == pytest.approx(0.5, abs=0.001)
    # 第三行：(398 - 402) / 402 * 100 ≈ -0.995
    assert result[2].return_pct == pytest.approx(-0.995, abs=0.001)


def test_fetch_etf_flows_returns_empty_on_http_error():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("429 Too Many Requests")
    with patch("app.services.etf.fetcher.httpx.get", return_value=mock_resp):
        result = fetch_etf_flows("SPY", "1mo")

    assert result == []


def test_fetch_etf_flows_returns_empty_on_no_historical():
    payload = {"symbol": "SPY", "historical": []}
    with patch("app.services.etf.fetcher.httpx.get", return_value=_mock_httpx_get(payload)):
        result = fetch_etf_flows("SPY", "1mo")

    assert result == []


def test_tracked_etfs_has_required_fields():
    for etf in TRACKED_ETFS:
        assert "symbol" in etf
        assert "name" in etf
        assert "category" in etf


def test_tracked_etfs_contains_major_symbols():
    symbols = {e["symbol"] for e in TRACKED_ETFS}
    assert {"SPY", "QQQ", "IWM", "GLD", "TLT"}.issubset(symbols)


def test_fetch_etf_list_summary_returns_one_summary_per_etf():
    payload = _make_fmp_response([400.0, 402.0], [50_000_000, 55_000_000])
    with patch("app.services.etf.fetcher.httpx.get", return_value=_mock_httpx_get(payload)):
        result = fetch_etf_list_summary("1mo")

    assert len(result) == len(TRACKED_ETFS)
    assert result[0].symbol == TRACKED_ETFS[0]["symbol"]
    assert result[0].period_dollar_volume > 0
