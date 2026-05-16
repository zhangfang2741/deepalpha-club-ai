"""ETF 偏离分计算函数和 API 端点单元测试。"""

import json
import zlib
from unittest.mock import AsyncMock, patch

import pytest

from app.services.etf.deviation import (
    build_deviation_response,
    compute_deviations,
    compute_market_avg,
    compute_scores,
)


# ── compute_market_avg ────────────────────────────────────────────────────────


def test_compute_market_avg_single_symbol():
    """单只 ETF 时 market_avg 等于该 ETF 自身强度。"""
    si = {"SPY": {"2026-01-02": 1.0, "2026-01-03": -0.5}}
    avg = compute_market_avg(si)
    assert avg["2026-01-02"] == pytest.approx(1.0)
    assert avg["2026-01-03"] == pytest.approx(-0.5)


def test_compute_market_avg_two_symbols():
    """两只 ETF market_avg = 均值。"""
    si = {
        "SPY": {"2026-01-02": 1.0},
        "QQQ": {"2026-01-02": 3.0},
    }
    avg = compute_market_avg(si)
    assert avg["2026-01-02"] == pytest.approx(2.0)


def test_compute_market_avg_missing_date_for_one_symbol():
    """某日只有一只 ETF 有数据，market_avg = 该 ETF 强度。"""
    si = {
        "SPY": {"2026-01-02": 1.0, "2026-01-03": 0.5},
        "QQQ": {"2026-01-02": 3.0},
    }
    avg = compute_market_avg(si)
    assert avg["2026-01-02"] == pytest.approx(2.0)
    assert avg["2026-01-03"] == pytest.approx(0.5)


def test_compute_market_avg_empty_returns_empty():
    assert compute_market_avg({}) == {}


# ── compute_deviations ────────────────────────────────────────────────────────


def test_compute_deviations_subtracts_market_avg():
    si = {"SPY": {"2026-01-02": 2.0}}
    avg = {"2026-01-02": 1.5}
    devs = compute_deviations(si, avg)
    assert devs["SPY"]["2026-01-02"] == pytest.approx(0.5)


def test_compute_deviations_skips_dates_without_market_avg():
    """日期不在 market_avg 中时跳过（防御性）。"""
    si = {"SPY": {"2026-01-02": 2.0, "2026-01-03": 1.0}}
    avg = {"2026-01-02": 1.5}
    devs = compute_deviations(si, avg)
    assert "2026-01-03" not in devs.get("SPY", {})


def test_compute_deviations_negative_values():
    si = {"TLT": {"2026-01-02": -1.0}}
    avg = {"2026-01-02": 0.5}
    devs = compute_deviations(si, avg)
    assert devs["TLT"]["2026-01-02"] == pytest.approx(-1.5)


# ── compute_scores ────────────────────────────────────────────────────────────


def test_compute_scores_panic_only():
    """只有恐慌期数据时，greed_score=None，overall=None。"""
    devs = {"SPY": {"2026-01-02": 0.8, "2026-01-03": 0.4}}
    fg = {"2026-01-02": 30.0, "2026-01-03": 40.0}
    scores = compute_scores(devs, fg)
    panic, greed, overall, pd, gd = scores["SPY"]
    assert panic == pytest.approx(0.6)
    assert greed is None
    assert overall is None
    assert pd == 2
    assert gd == 0


def test_compute_scores_greed_only():
    """只有贪婪期数据时，panic_score=None，overall=None。"""
    devs = {"SPY": {"2026-01-02": 1.0}}
    fg = {"2026-01-02": 80.0}
    scores = compute_scores(devs, fg)
    panic, greed, overall, pd, gd = scores["SPY"]
    assert panic is None
    assert greed == pytest.approx(1.0)
    assert overall is None
    assert pd == 0
    assert gd == 1


def test_compute_scores_both_periods():
    """恐慌和贪婪期都有数据，overall = (panic + greed) / 2。"""
    devs = {"SPY": {"2026-01-02": 1.0, "2026-01-03": 0.5}}
    fg = {"2026-01-02": 30.0, "2026-01-03": 70.0}
    scores = compute_scores(devs, fg)
    panic, greed, overall, pd, gd = scores["SPY"]
    assert panic == pytest.approx(1.0)
    assert greed == pytest.approx(0.5)
    assert overall == pytest.approx(0.75)


def test_compute_scores_neutral_dates_excluded():
    """中性期（45 <= FG <= 55）不参与任何计算。"""
    devs = {"SPY": {"2026-01-02": 99.0, "2026-01-03": 1.0, "2026-01-04": 2.0}}
    fg = {"2026-01-02": 50.0, "2026-01-03": 20.0, "2026-01-04": 80.0}
    scores = compute_scores(devs, fg)
    panic, greed, overall, pd, gd = scores["SPY"]
    assert pd == 1
    assert gd == 1
    assert panic == pytest.approx(1.0)
    assert greed == pytest.approx(2.0)


def test_compute_scores_no_fg_overlap_returns_nones():
    """symbol 的日期与 fg_by_date 完全不重叠，全部为 None。"""
    devs = {"SPY": {"2026-01-02": 1.0}}
    fg = {"2025-01-02": 30.0}
    scores = compute_scores(devs, fg)
    panic, greed, overall, pd, gd = scores["SPY"]
    assert panic is None
    assert greed is None
    assert overall is None
    assert pd == 0
    assert gd == 0


def test_compute_scores_negative_deviation():
    """负偏离分应正确计算。"""
    devs = {"SPY": {"2026-01-02": -1.5}}
    fg = {"2026-01-02": 25.0}
    scores = compute_scores(devs, fg)
    panic, _, _, _, _ = scores["SPY"]
    assert panic == pytest.approx(-1.5)


def test_compute_scores_custom_thresholds():
    """自定义阈值正确生效。"""
    devs = {"SPY": {"2026-01-02": 0.5}}
    fg = {"2026-01-02": 48.0}
    scores_default = compute_scores(devs, fg)
    scores_custom = compute_scores(devs, fg, panic_threshold=50.0, greed_threshold=60.0)
    assert scores_default["SPY"][0] is None
    assert scores_custom["SPY"][0] == pytest.approx(0.5)


def test_compute_scores_multiple_symbols():
    """多只 ETF 各自计算，互不干扰。"""
    devs = {
        "SPY": {"2026-01-02": 1.0},
        "TLT": {"2026-01-02": -1.0},
    }
    fg = {"2026-01-02": 20.0}
    scores = compute_scores(devs, fg)
    assert scores["SPY"][0] == pytest.approx(1.0)
    assert scores["TLT"][0] == pytest.approx(-1.0)


# ── build_deviation_response ──────────────────────────────────────────────────


def test_build_deviation_response_structure():
    """build_deviation_response 返回正确结构，板块按 ETF_LIBRARY 顺序。"""
    from app.schemas.fear_greed import FearGreedPoint, FearGreedSnapshot

    si = {"XLK": {"2026-01-02": 0.5}, "TLT": {"2026-01-02": -0.5}}
    fg_history = [
        FearGreedPoint(date="2026-01-02", score=30.0, rating="Fear")
    ]
    fg_current = FearGreedSnapshot(score=65.0, rating="Greed")

    result = build_deviation_response(si, fg_history, fg_current, days=30)

    assert result.fg_score == 65.0
    assert result.fg_rating == "Greed"
    assert result.days == 30
    assert len(result.sectors) > 0
    sector_names = [s.sector for s in result.sectors]
    assert "01 信息技术" in sector_names


def test_build_deviation_response_sector_avg():
    """板块均值在所有 ETF overall_score 不为 None 时正确计算。"""
    from app.schemas.fear_greed import FearGreedPoint, FearGreedSnapshot

    si = {
        "XLK": {"2026-01-02": 1.0},
        "SOXX": {"2026-01-02": 0.5},
    }
    # 恐慌期：FG = 30
    fg_history = [FearGreedPoint(date="2026-01-02", score=30.0, rating="Fear")]
    fg_current = FearGreedSnapshot(score=30.0, rating="Fear")

    result = build_deviation_response(si, fg_history, fg_current, days=30)

    sector_it = next(s for s in result.sectors if s.sector == "01 信息技术")
    xlk = next((e for e in sector_it.etfs if e.symbol == "XLK"), None)
    assert xlk is not None
    assert xlk.panic_days == 1


def test_build_deviation_response_empty_si():
    """symbol_intensity 为空时返回空 sectors etfs 列表，不抛异常。"""
    from app.schemas.fear_greed import FearGreedPoint, FearGreedSnapshot

    fg_history = [FearGreedPoint(date="2026-01-02", score=30.0, rating="Fear")]
    fg_current = FearGreedSnapshot(score=30.0, rating="Fear")

    result = build_deviation_response({}, fg_history, fg_current, days=30)
    assert result.days == 30
    for sector in result.sectors:
        for etf in sector.etfs:
            assert etf.panic_score is None
            assert etf.greed_score is None


# ── Schema 验证测试 ───────────────────────────────────────────────────────────


def test_etf_deviation_score_schema():
    from app.schemas.etf import ETFDeviationScore

    score = ETFDeviationScore(
        symbol="SPY",
        name="标普500",
        sector="12 全球宏观/另类",
        panic_score=None,
        greed_score=None,
        overall_score=None,
        panic_days=0,
        greed_days=0,
    )
    assert score.panic_score is None
    assert score.overall_score is None


def test_deviation_score_response_serializable():
    """model_dump(mode='json') 不抛异常，用于缓存写入。"""
    from app.schemas.etf import DeviationScoreResponse, ETFDeviationScore, SectorDeviationGroup

    resp = DeviationScoreResponse(
        days=30,
        fg_score=65.0,
        fg_rating="Greed",
        sectors=[
            SectorDeviationGroup(
                sector="01 信息技术",
                avg_panic_score=0.5,
                avg_greed_score=1.2,
                avg_overall_score=0.85,
                etfs=[
                    ETFDeviationScore(
                        symbol="XLK",
                        name="科技",
                        sector="01 信息技术",
                        panic_score=0.5,
                        greed_score=1.2,
                        overall_score=0.85,
                        panic_days=3,
                        greed_days=8,
                    )
                ],
            )
        ],
    )
    data = resp.model_dump(mode="json")
    assert data["fg_score"] == 65.0
    assert data["sectors"][0]["avg_overall_score"] == pytest.approx(0.85)


# ── 缓存函数测试 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_deviation_cache_miss():
    from app.cache.etf_cache import get_deviation_cache

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    result = await get_deviation_cache(mock_redis, days=30)
    assert result is None


@pytest.mark.asyncio
async def test_get_deviation_cache_hit():
    from app.cache.etf_cache import get_deviation_cache
    from app.schemas.etf import DeviationScoreResponse

    mock_redis = AsyncMock()
    data = DeviationScoreResponse(days=30, fg_score=65.0, fg_rating="Greed", sectors=[])
    payload = zlib.compress(
        json.dumps(data.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
    )
    mock_redis.get.return_value = payload
    result = await get_deviation_cache(mock_redis, days=30)
    assert result is not None
    assert result.fg_score == 65.0


@pytest.mark.asyncio
async def test_set_deviation_cache_writes_correct_key():
    from app.cache.etf_cache import set_deviation_cache
    from app.schemas.etf import DeviationScoreResponse

    mock_redis = AsyncMock()
    data = DeviationScoreResponse(days=30, fg_score=65.0, fg_rating="Greed", sectors=[])
    await set_deviation_cache(mock_redis, days=30, data=data)
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    assert call_args[0][0] == "etf:deviation:30"
    assert call_args[1]["ex"] == 3600


@pytest.mark.asyncio
async def test_get_deviation_cache_handles_corrupt_data():
    """损坏的缓存数据返回 None 而非抛异常。"""
    from app.cache.etf_cache import get_deviation_cache

    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"not_valid_zlib_or_json"
    result = await get_deviation_cache(mock_redis, days=30)
    assert result is None
