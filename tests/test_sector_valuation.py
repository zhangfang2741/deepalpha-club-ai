"""行业估值 z-score 功能单元测试。"""

import json
import zlib
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.schemas.valuation import SectorValuation, SectorValuationResponse
from app.services.valuation.sector_pe import (
    _pe_from_record,
    compute_z_score,
    get_valuation_label,
    build_sector_valuation,
    _quarter_end_dates,
)


# ─── compute_z_score ──────────────────────────────────────────────────────────

def test_z_score_positive_when_above_mean():
    values = [10.0, 15.0, 20.0, 25.0, 30.0]
    result = compute_z_score(values, current=35.0)
    assert result is not None
    assert result > 0


def test_z_score_negative_when_below_mean():
    values = [10.0, 15.0, 20.0, 25.0, 30.0]
    result = compute_z_score(values, current=5.0)
    assert result is not None
    assert result < 0


def test_z_score_near_zero_at_mean():
    values = [10.0, 20.0, 30.0]
    result = compute_z_score(values, current=20.0)
    assert result == pytest.approx(0.0, abs=1e-9)


def test_z_score_none_when_insufficient_data():
    assert compute_z_score([], current=10.0) is None
    assert compute_z_score([10.0], current=10.0) is None


def test_z_score_none_when_zero_std():
    values = [15.0, 15.0, 15.0, 15.0]
    assert compute_z_score(values, current=15.0) is None


# ─── get_valuation_label ──────────────────────────────────────────────────────

@pytest.mark.parametrize("z,expected_label", [
    (-3.0, "极度低估"),
    (-2.0, "极度低估"),
    (-1.5, "低估"),
    (-1.0, "低估"),
    (0.0, "中性"),
    (0.99, "中性"),
    (1.0, "高估"),
    (1.5, "高估"),
    (2.0, "极度高估"),
    (3.0, "极度高估"),
])
def test_valuation_label_thresholds(z, expected_label):
    label, _ = get_valuation_label(z)
    assert label == expected_label


def test_valuation_label_none_z_score():
    label, label_en = get_valuation_label(None)
    assert label == "数据不足"
    assert label_en == "insufficient"


def test_valuation_label_returns_english_key():
    _, en = get_valuation_label(-2.5)
    assert en == "extreme_undervalue"
    _, en = get_valuation_label(2.5)
    assert en == "extreme_overvalue"


# ─── _pe_from_record ─────────────────────────────────────────────────────────

def test_pe_from_record_pe_field():
    record = {"date": "2024-09-30", "sector": "Technology", "pe": 28.5}
    assert _pe_from_record(record) == pytest.approx(28.5)


def test_pe_from_record_fallback_peRatio_field():
    record = {"date": "2024-09-30", "sector": "Technology", "peRatio": 28.5}
    assert _pe_from_record(record) == pytest.approx(28.5)


def test_pe_from_record_none_when_missing():
    record = {"date": "2024-09-30", "sector": "Technology"}
    assert _pe_from_record(record) is None


def test_pe_from_record_none_when_zero():
    record = {"date": "2024-09-30", "pe": 0}
    assert _pe_from_record(record) is None


def test_pe_from_record_skips_negative():
    record = {"date": "2024-09-30", "pe": -5.0}
    assert _pe_from_record(record) is None


# ─── _quarter_end_dates ───────────────────────────────────────────────────────

def test_quarter_end_dates_count():
    dates = _quarter_end_dates(years=10)
    assert len(dates) == 40


def test_quarter_end_dates_descending():
    dates = _quarter_end_dates(years=10)
    assert dates == sorted(dates, reverse=True)


def test_quarter_end_dates_all_in_past():
    today_str = date.today().strftime("%Y-%m-%d")
    dates = _quarter_end_dates(years=10)
    for d in dates:
        assert d < today_str


# ─── build_sector_valuation ──────────────────────────────────────────────────

def _make_pe_series(dates_pes: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """最新在前。"""
    return sorted(dates_pes, key=lambda x: x[0], reverse=True)


def test_build_sector_valuation_basic():
    pe_series = _make_pe_series([
        ("2015-03-31", 10.0), ("2015-06-30", 12.0), ("2015-09-30", 14.0),
        ("2015-12-31", 16.0), ("2016-03-31", 18.0), ("2016-06-30", 20.0),
        ("2024-09-30", 30.0),  # current = 30 → above mean
    ])
    sv = build_sector_valuation(
        sector="Technology",
        sector_cn="信息技术",
        pe_series=pe_series,
    )
    assert sv.sector == "Technology"
    assert sv.sector_cn == "信息技术"
    assert sv.current_pe == pytest.approx(30.0)
    assert sv.z_score is not None
    assert sv.z_score > 0
    assert sv.label in ("高估", "极度高估")
    assert len(sv.hist_pe) == 7
    # hist_pe 应该按升序排列（最早在前）
    assert sv.hist_pe[0]["date"] < sv.hist_pe[-1]["date"]


def test_build_sector_valuation_insufficient_data():
    pe_series = _make_pe_series([("2024-09-30", 25.0)])
    sv = build_sector_valuation("Technology", "信息技术", pe_series)
    assert sv.z_score is None
    assert sv.label == "数据不足"
    assert sv.current_pe == pytest.approx(25.0)


def test_build_sector_valuation_empty_series():
    sv = build_sector_valuation("Technology", "信息技术", [])
    assert sv.z_score is None
    assert sv.current_pe is None
    assert sv.label == "数据不足"


def test_build_sector_valuation_low_z_score():
    """近期 PE 远低于历史均值 → 极度低估。"""
    hist = [(f"201{y}-{m:02d}-{d:02d}", 30.0)
            for y in range(5, 10) for m, d in [(3, 31), (6, 30), (9, 30), (12, 31)]]
    # current PE = 10（远低于历史均值 30）
    pe_series = _make_pe_series(hist + [("2024-09-30", 10.0)])
    sv = build_sector_valuation("Energy", "能源", pe_series)
    assert sv.z_score is not None
    assert sv.z_score < -2
    assert sv.label == "极度低估"


# ─── Schema validation ────────────────────────────────────────────────────────

def test_sector_valuation_schema():
    sv = SectorValuation(
        sector="Energy",
        sector_cn="能源",
        etf_symbol="",
        current_pe=None,
        hist_mean=None,
        hist_std=None,
        z_score=None,
        label="数据不足",
        label_en="insufficient",
        hist_pe=[],
        data_quarters=0,
    )
    assert sv.z_score is None


def test_sector_valuation_response_serializable():
    resp = SectorValuationResponse(
        as_of="2024-09-30",
        sectors=[
            SectorValuation(
                sector="Technology",
                sector_cn="信息技术",
                etf_symbol="",
                current_pe=30.5,
                hist_mean=22.0,
                hist_std=5.0,
                z_score=1.7,
                label="高估",
                label_en="overvalue",
                hist_pe=[{"date": "2024-09-30", "pe": 30.5}],
                data_quarters=40,
            )
        ],
    )
    data = resp.model_dump(mode="json")
    assert data["as_of"] == "2024-09-30"
    assert len(data["sectors"]) == 1
    assert data["sectors"][0]["z_score"] == pytest.approx(1.7)


# ─── Cache ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valuation_cache_miss():
    from app.cache.valuation_cache import get_valuation_cache

    redis = AsyncMock()
    redis.get.return_value = None
    result = await get_valuation_cache(redis)
    assert result is None


@pytest.mark.asyncio
async def test_valuation_cache_hit():
    from app.cache.valuation_cache import get_valuation_cache

    resp = SectorValuationResponse(as_of="2024-09-30", sectors=[])
    payload = zlib.compress(json.dumps(resp.model_dump(mode="json")).encode())
    redis = AsyncMock()
    redis.get.return_value = payload
    result = await get_valuation_cache(redis)
    assert result is not None
    assert result.as_of == "2024-09-30"


@pytest.mark.asyncio
async def test_valuation_cache_set_correct_key():
    from app.cache.valuation_cache import set_valuation_cache

    redis = AsyncMock()
    resp = SectorValuationResponse(as_of="2024-09-30", sectors=[])
    await set_valuation_cache(redis, resp)
    redis.set.assert_called_once()
    key_arg = redis.set.call_args[0][0]
    assert key_arg == "valuation:sectors"


@pytest.mark.asyncio
async def test_valuation_cache_handles_corrupt():
    from app.cache.valuation_cache import get_valuation_cache

    redis = AsyncMock()
    redis.get.return_value = b"not-valid-json-or-zlib"
    result = await get_valuation_cache(redis)
    assert result is None
