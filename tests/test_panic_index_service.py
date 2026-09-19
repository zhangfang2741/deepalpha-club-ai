"""三地恐慌指数服务单元测试（mock akshare 数据源与 Redis 缓存）。"""

from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from app.schemas.panic_index import PanicIndexResponse
from app.services.panic_index import (
    _build_from_price_df,
    _price_to_points,
    _RawPoint,
    _score_to_rating,
    get_panic_index,
)


def test_score_to_rating_boundaries():
    assert _score_to_rating(0) == "Extreme Fear"
    assert _score_to_rating(24.9) == "Extreme Fear"
    assert _score_to_rating(25) == "Fear"
    assert _score_to_rating(55.9) == "Neutral"
    assert _score_to_rating(76) == "Extreme Greed"


def test_price_to_points_drops_rsi_warmup_period():
    """前 14 个点没有 RSI，不进历史序列。"""
    raw = [_RawPoint(date=f"2026-01-{i:02d}", close=float(100 + i)) for i in range(1, 20)]
    points = _price_to_points(raw)
    assert len(points) == len(raw) - 14


def test_price_to_points_monotonic_rise_gives_extreme_greed():
    """单调上涨 → RSI=100 → 分数=100 → Extreme Greed。"""
    raw = [_RawPoint(date=f"2026-01-{i:02d}", close=float(100 + i)) for i in range(1, 20)]
    points = _price_to_points(raw)
    assert points[0].score == pytest.approx(100.0)
    assert points[0].rating == "Extreme Greed"
    # raw_value 应该是指数收盘价而不是波动率
    assert points[0].raw_value == raw[14].close


def test_price_to_points_monotonic_fall_gives_extreme_fear():
    """单调下跌 → RSI=0 → 分数=0 → Extreme Fear。"""
    raw = [_RawPoint(date=f"2026-01-{i:02d}", close=float(120 - i)) for i in range(1, 20)]
    points = _price_to_points(raw)
    assert points[0].score == pytest.approx(0.0)
    assert points[0].rating == "Extreme Fear"


@pytest.mark.asyncio
async def test_build_from_price_df_sorts_and_caches():
    """DataFrame 乱序也要按日期排好序，并写入缓存。"""
    dates = [f"2026-01-{i:02d}" for i in range(1, 20)]
    closes = [100.0 + i for i in range(19)]
    # 打乱顺序，验证内部会重新按日期排序
    df = pd.DataFrame({"date": list(reversed(dates)), "close": list(reversed(closes))})

    mock_redis = AsyncMock()
    with patch("app.services.panic_index.set_panic_index_cache", new_callable=AsyncMock) as mock_set:
        resp = await _build_from_price_df(mock_redis, market="cn", df=df)

    assert resp.market == "cn"
    assert resp.current.date == dates[-1]
    assert resp.history[0].date == dates[14]  # 前 14 天预热期被丢弃
    mock_set.assert_called_once()


@pytest.mark.asyncio
async def test_build_from_price_df_filters_non_positive_close():
    """close<=0 的脏数据要被过滤掉，不能进 RSI 计算。"""
    dates = [f"2026-01-{i:02d}" for i in range(1, 21)]
    closes = [100.0 + i for i in range(19)] + [0.0]
    df = pd.DataFrame({"date": dates, "close": closes})

    mock_redis = AsyncMock()
    with patch("app.services.panic_index.set_panic_index_cache", new_callable=AsyncMock):
        resp = await _build_from_price_df(mock_redis, market="hk", df=df)

    assert all(p.raw_value != 0.0 for p in resp.history)


@pytest.mark.asyncio
async def test_get_panic_index_returns_cached_data():
    """缓存命中时直接返回，不触发 builder（不调用 akshare）。"""
    cached = PanicIndexResponse.model_validate({
        "market": "cn",
        "label": "A股情绪 (上证指数 RSI)",
        "current": {"score": 70, "rating": "Greed", "date": "2026-09-18"},
        "previous_week": {"score": 60, "rating": "Greed"},
        "previous_month": {"score": 50, "rating": "Neutral"},
        "history": [],
    })
    mock_redis = AsyncMock()
    with (
        patch("app.services.panic_index.get_panic_index_cache", new_callable=AsyncMock, return_value=cached) as mock_get,
        patch("app.services.panic_index._fetch_cn_index") as mock_fetch,
    ):
        result = await get_panic_index(mock_redis, "cn")

    assert result.current.score == 70
    mock_get.assert_called_once_with(mock_redis, "cn")
    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_get_panic_index_unsupported_market_raises():
    mock_redis = AsyncMock()
    with pytest.raises(ValueError):
        await get_panic_index(mock_redis, "jp")
