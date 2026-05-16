"""ETF 错杀分（历史自身对比）计算函数和 API 单元测试。"""

import json
import zlib
from unittest.mock import AsyncMock

import pytest

from app.services.etf.deviation import (
    build_deviation_response,
    compute_historical_scores,
)


# ── compute_historical_scores ─────────────────────────────────────────────────


def test_historical_scores_panic_below_history():
    """近期恐慌期强度低于历史 → panic_score 为负（被错杀）。"""
    # 历史：恐慌日强度 1.0；近期：恐慌日强度 -0.5
    si = {"SPY": {
        "2025-01-02": 1.0, "2025-01-03": 1.2,   # 历史恐慌日
        "2026-01-02": -0.5,                        # 近期恐慌日
    }}
    fg = {"2025-01-02": 30.0, "2025-01-03": 35.0, "2026-01-02": 28.0}
    recent = {"2026-01-02"}

    scores = compute_historical_scores(si, fg, recent)
    panic, greed, overall, pd, gd = scores["SPY"]
    # hist_panic_avg = mean(1.0, 1.2, -0.5) = 0.567; recent = -0.5
    # panic_score = -0.5 - 0.567 ≈ -1.067
    assert panic is not None
    assert panic < 0
    assert pd == 1
    assert greed is None


def test_historical_scores_panic_above_history():
    """近期恐慌期强度高于历史 → panic_score 为正（异常强势）。"""
    si = {"TLT": {
        "2025-01-02": -0.5, "2025-01-03": -0.3,  # 历史恐慌日
        "2026-01-02": 2.0,                          # 近期恐慌日
    }}
    fg = {"2025-01-02": 20.0, "2025-01-03": 25.0, "2026-01-02": 15.0}
    recent = {"2026-01-02"}

    scores = compute_historical_scores(si, fg, recent)
    panic, _, _, _, _ = scores["TLT"]
    assert panic is not None
    assert panic > 0


def test_historical_scores_no_recent_panic():
    """近期无恐慌日（全为贪婪期）→ panic_score=None。"""
    si = {"QQQ": {
        "2025-01-02": 1.0,  # 历史恐慌日
        "2026-01-02": 0.5,  # 近期贪婪日
    }}
    fg = {"2025-01-02": 30.0, "2026-01-02": 80.0}
    recent = {"2026-01-02"}

    scores = compute_historical_scores(si, fg, recent)
    panic, greed, overall, pd, gd = scores["QQQ"]
    assert panic is None
    assert pd == 0
    assert greed is not None
    assert gd == 1


def test_historical_scores_no_hist_panic():
    """所有日期均无恐慌日（FG 全为贪婪期）→ panic_score=None。"""
    si = {"QQQ": {
        "2025-01-02": 1.0,  # 历史贪婪日
        "2026-01-02": 0.5,  # 近期贪婪日
    }}
    fg = {"2025-01-02": 80.0, "2026-01-02": 75.0}
    recent = {"2026-01-02"}

    scores = compute_historical_scores(si, fg, recent)
    panic, greed, _, pd, gd = scores["QQQ"]
    assert panic is None
    assert pd == 0
    assert greed is not None  # 贪婪期有数据


def test_historical_scores_only_recent_panic():
    """唯一的恐慌日就在近期窗口（也属于历史），score=0.0（recent==hist）。"""
    si = {"QQQ": {
        "2025-01-02": 1.0,  # 历史贪婪日
        "2026-01-02": -0.5, # 近期恐慌日（同时也是历史唯一恐慌日）
    }}
    fg = {"2025-01-02": 80.0, "2026-01-02": 20.0}
    recent = {"2026-01-02"}

    scores = compute_historical_scores(si, fg, recent)
    panic, _, _, pd, _ = scores["QQQ"]
    # hist_panic_avg = -0.5（仅这一天），recent_panic_avg = -0.5 → score = 0.0
    assert panic == pytest.approx(0.0)
    assert pd == 1


def test_historical_scores_no_fg_overlap():
    """FG 日期与 ETF 日期完全不重叠 → 全部 None。"""
    si = {"SPY": {"2026-01-02": 1.0}}
    fg = {"2025-01-02": 30.0}
    recent = {"2026-01-02"}

    scores = compute_historical_scores(si, fg, recent)
    panic, greed, overall, pd, gd = scores["SPY"]
    assert panic is None
    assert greed is None
    assert overall is None
    assert pd == 0
    assert gd == 0


def test_historical_scores_both_periods():
    """恐慌和贪婪期都有近期+历史数据 → overall = (panic + greed) / 2。"""
    si = {"XLK": {
        "2025-01-02": 1.0,  # 历史恐慌
        "2025-01-03": 0.8,  # 历史贪婪
        "2026-01-02": -0.5, # 近期恐慌
        "2026-01-03": 2.0,  # 近期贪婪
    }}
    fg = {
        "2025-01-02": 20.0, "2025-01-03": 80.0,
        "2026-01-02": 25.0, "2026-01-03": 75.0,
    }
    recent = {"2026-01-02", "2026-01-03"}

    scores = compute_historical_scores(si, fg, recent)
    panic, greed, overall, pd, gd = scores["XLK"]
    assert panic is not None
    assert greed is not None
    assert overall is not None
    assert overall == pytest.approx((panic + greed) / 2)
    assert pd == 1
    assert gd == 1


def test_historical_scores_neutral_ignored():
    """FG 在中性区间（45-55）的日期不参与任何计算。"""
    si = {"SPY": {
        "2026-01-02": 99.0, # 近期中性日
        "2025-01-02": 1.0,  # 历史恐慌日
        "2026-01-03": -1.0, # 近期恐慌日
    }}
    fg = {"2026-01-02": 50.0, "2025-01-02": 30.0, "2026-01-03": 20.0}
    recent = {"2026-01-02", "2026-01-03"}

    scores = compute_historical_scores(si, fg, recent)
    _, _, _, pd, gd = scores["SPY"]
    assert pd == 1   # 只有 2026-01-03 计入近期恐慌
    assert gd == 0


def test_historical_scores_multiple_symbols():
    """多只 ETF 各自独立计算，互不影响。"""
    si = {
        "SPY": {"2025-01-02": 1.0, "2026-01-02": -1.0},
        "TLT": {"2025-01-02": -0.5, "2026-01-02": 0.5},
    }
    fg = {"2025-01-02": 30.0, "2026-01-02": 25.0}
    recent = {"2026-01-02"}

    scores = compute_historical_scores(si, fg, recent)
    spy_panic, _, _, _, _ = scores["SPY"]
    tlt_panic, _, _, _, _ = scores["TLT"]
    # SPY: recent=-1.0, hist=mean(1.0, -1.0)=0 → score=-1.0
    # TLT: recent=0.5,  hist=mean(-0.5, 0.5)=0 → score=0.5
    assert spy_panic < 0
    assert tlt_panic > 0


def test_historical_scores_custom_thresholds():
    """自定义阈值生效。"""
    si = {"SPY": {"2026-01-02": 0.5}}
    fg = {"2026-01-02": 48.0}
    recent = {"2026-01-02"}

    # 默认 panic_threshold=45：48 不是恐慌期
    scores_default = compute_historical_scores(si, fg, recent)
    assert scores_default["SPY"][0] is None

    # 自定义 panic_threshold=50：48 是恐慌期（但无历史基准，所以仍为 None）
    scores_custom = compute_historical_scores(si, fg, recent, panic_threshold=50.0)
    # 近期有恐慌日但历史也只有这一天，recent == hist，score = 0.0
    assert scores_custom["SPY"][0] == pytest.approx(0.0)


# ── build_deviation_response ──────────────────────────────────────────────────


def test_build_deviation_response_includes_days_hist():
    """response 中包含 days_hist 字段。"""
    from app.schemas.fear_greed import FearGreedPoint, FearGreedSnapshot

    si = {}
    fg_history: list = []
    fg_current = FearGreedSnapshot(score=65.0, rating="Greed")

    result = build_deviation_response(si, fg_history, fg_current, recent_days=30, days_hist=365)
    assert result.days == 30
    assert result.days_hist == 365


def test_build_deviation_response_sectors_present():
    """response 包含所有 ETF_LIBRARY 中的板块。"""
    from app.schemas.fear_greed import FearGreedPoint, FearGreedSnapshot

    fg_history = [
        FearGreedPoint(date="2025-01-02", score=30.0, rating="Fear"),
        FearGreedPoint(date="2026-01-02", score=28.0, rating="Fear"),
    ]
    fg_current = FearGreedSnapshot(score=30.0, rating="Fear")
    si = {
        "XLK": {"2025-01-02": 1.0, "2026-01-02": -0.5},
    }

    result = build_deviation_response(si, fg_history, fg_current, recent_days=30, days_hist=365)
    sector_names = [s.sector for s in result.sectors]
    assert "01 信息技术" in sector_names
    assert len(result.sectors) > 0


def test_build_deviation_response_empty_si():
    """symbol_intensity 为空时不抛异常，所有 ETF 分数为 None。"""
    from app.schemas.fear_greed import FearGreedPoint, FearGreedSnapshot

    fg_current = FearGreedSnapshot(score=30.0, rating="Fear")
    result = build_deviation_response({}, [], fg_current, recent_days=30, days_hist=365)
    for sector in result.sectors:
        for etf in sector.etfs:
            assert etf.panic_score is None
            assert etf.greed_score is None


# ── Schema 验证 ────────────────────────────────────────────────────────────────


def test_etf_deviation_score_schema():
    from app.schemas.etf import ETFDeviationScore

    score = ETFDeviationScore(
        symbol="SPY", name="标普500", sector="12 全球宏观/另类",
        panic_score=None, greed_score=None, overall_score=None,
        panic_days=0, greed_days=0,
    )
    assert score.panic_score is None


def test_deviation_score_response_has_days_hist():
    from app.schemas.etf import DeviationScoreResponse

    resp = DeviationScoreResponse(
        days=30, days_hist=365, fg_score=65.0, fg_rating="Greed", sectors=[]
    )
    assert resp.days_hist == 365


def test_deviation_response_serializable():
    from app.schemas.etf import DeviationScoreResponse, ETFDeviationScore, SectorDeviationGroup

    resp = DeviationScoreResponse(
        days=30, days_hist=365, fg_score=65.0, fg_rating="Greed",
        sectors=[SectorDeviationGroup(
            sector="01 信息技术",
            avg_panic_score=-0.5, avg_greed_score=0.3, avg_overall_score=-0.1,
            etfs=[ETFDeviationScore(
                symbol="XLK", name="科技", sector="01 信息技术",
                panic_score=-0.5, greed_score=0.3, overall_score=-0.1,
                panic_days=5, greed_days=8,
            )],
        )],
    )
    data = resp.model_dump(mode="json")
    assert data["days_hist"] == 365
    assert data["sectors"][0]["avg_panic_score"] == pytest.approx(-0.5)


# ── 缓存函数测试 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_deviation_cache_miss():
    from app.cache.etf_cache import get_deviation_cache

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    result = await get_deviation_cache(mock_redis, days=30, days_hist=365)
    assert result is None


@pytest.mark.asyncio
async def test_get_deviation_cache_hit():
    from app.cache.etf_cache import get_deviation_cache
    from app.schemas.etf import DeviationScoreResponse

    mock_redis = AsyncMock()
    data = DeviationScoreResponse(days=30, days_hist=365, fg_score=65.0, fg_rating="Greed", sectors=[])
    payload = zlib.compress(
        json.dumps(data.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
    )
    mock_redis.get.return_value = payload
    result = await get_deviation_cache(mock_redis, days=30, days_hist=365)
    assert result is not None
    assert result.fg_score == 65.0
    assert result.days_hist == 365


@pytest.mark.asyncio
async def test_set_deviation_cache_writes_correct_key():
    from app.cache.etf_cache import set_deviation_cache
    from app.schemas.etf import DeviationScoreResponse

    mock_redis = AsyncMock()
    data = DeviationScoreResponse(days=30, days_hist=365, fg_score=65.0, fg_rating="Greed", sectors=[])
    await set_deviation_cache(mock_redis, days=30, days_hist=365, data=data)
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    assert call_args[0][0] == "etf:deviation:30:365"
    assert call_args[1]["ex"] == 3600


@pytest.mark.asyncio
async def test_get_deviation_cache_handles_corrupt_data():
    from app.cache.etf_cache import get_deviation_cache

    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"not_valid_zlib_or_json"
    result = await get_deviation_cache(mock_redis, days=30, days_hist=365)
    assert result is None
