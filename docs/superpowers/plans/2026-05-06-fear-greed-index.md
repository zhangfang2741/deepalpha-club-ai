# Fear & Greed Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `/fear-greed` 页面，通过后端代理 CNN API 获取并缓存恐慌贪婪指数历史数据，前端用 lightweight-charts v5 展示带情绪色带的折线图及 6 张统计卡片。

**Architecture:** 后端新增独立的 schema / cache / service / router 层，挂载到现有 `/api/v1` 路由聚合器；前端遵循 ETF 页面的 API → Store → 页面 → 组件模式，lightweight-charts 已预装（v5.2.0）。

**Tech Stack:** FastAPI + httpx（异步 HTTP 请求）+ Redis（TTL=3600s）+ Pydantic v2；Next.js 14 + Zustand + lightweight-charts v5

---

## 文件结构

**新增（后端）：**
- `app/schemas/fear_greed.py` — Pydantic 响应模型（FearGreedPoint / FearGreedSnapshot / FearGreedResponse）
- `app/cache/fear_greed_cache.py` — Redis get/set（key: `fear_greed:history:1y`，TTL 3600s）
- `app/services/fear_greed.py` — FearGreedService（调用 CNN API、解析、计算统计值、写缓存）
- `app/api/v1/fear_greed.py` — FastAPI router（`GET /fear-greed`）
- `tests/test_fear_greed_schema.py` — Schema 验证测试
- `tests/test_fear_greed_service.py` — Service 单元测试（mock CNN API）

**修改（后端）：**
- `app/api/v1/api.py` — 挂载 fear_greed router

**新增（前端）：**
- `frontend/lib/api/fear_greed.ts` — Axios API 层 + TypeScript 类型定义
- `frontend/lib/store/fear_greed.ts` — Zustand store
- `frontend/components/fear_greed/FearGreedChart.tsx` — lightweight-charts 折线图 + 情绪色带 + tooltip
- `frontend/app/(dashboard)/fear-greed/page.tsx` — 页面（加载/错误/数据状态 + 6 张统计卡片）

**修改（前端）：**
- `frontend/components/layout/TopNav.tsx` — 在 ETF 前插入 `{ href: '/fear-greed', label: '恐慌指数' }`

---

### Task 1: Backend Schemas

**Files:**
- Create: `app/schemas/fear_greed.py`
- Test: `tests/test_fear_greed_schema.py`

- [ ] **Step 1: 编写 failing schema 测试**

```python
# tests/test_fear_greed_schema.py
"""Fear & Greed Index schema 验证测试。"""
import pytest
from pydantic import ValidationError
from app.schemas.fear_greed import (
    FearGreedPoint,
    FearGreedSnapshot,
    FearGreedResponse,
)


def test_fear_greed_point_valid():
    point = FearGreedPoint(date="2025-05-06", score=38, rating="Fear")
    assert point.score == 38
    assert point.rating == "Fear"
    assert point.date == "2025-05-06"


def test_fear_greed_point_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        FearGreedPoint(date="2025-05-06", score=101, rating="Extreme Greed")


def test_fear_greed_point_rejects_negative_score():
    with pytest.raises(ValidationError):
        FearGreedPoint(date="2025-05-06", score=-1, rating="Extreme Fear")


def test_fear_greed_snapshot_no_date():
    snap = FearGreedSnapshot(score=72, rating="Greed")
    assert snap.score == 72
    assert snap.date is None


def test_fear_greed_snapshot_with_date():
    snap = FearGreedSnapshot(score=2, rating="Extreme Fear", date="2022-10-12")
    assert snap.date == "2022-10-12"


def test_fear_greed_response_structure():
    resp = FearGreedResponse(
        current=FearGreedSnapshot(score=72, rating="Greed", date="2026-05-06"),
        previous_week=FearGreedSnapshot(score=38, rating="Fear"),
        previous_month=FearGreedSnapshot(score=51, rating="Neutral"),
        previous_year=FearGreedSnapshot(score=52, rating="Neutral"),
        history_low=FearGreedSnapshot(score=2, rating="Extreme Fear", date="2022-10-12"),
        history_high=FearGreedSnapshot(score=97, rating="Extreme Greed", date="2021-11-09"),
        history=[FearGreedPoint(date="2025-05-06", score=38, rating="Fear")],
    )
    assert len(resp.history) == 1
    assert resp.current.score == 72
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_fear_greed_schema.py -v
```

预期：`FAILED` — `ModuleNotFoundError: No module named 'app.schemas.fear_greed'`

- [ ] **Step 3: 实现 `app/schemas/fear_greed.py`**

```python
"""Fear & Greed Index Pydantic schemas。"""
from typing import List, Optional

from pydantic import Field

from app.schemas.base import BaseResponse


class FearGreedPoint(BaseResponse):
    """历史数据中的单个数据点。"""

    date: str = Field(description="日期，格式 YYYY-MM-DD")
    score: float = Field(ge=0, le=100, description="恐慌贪婪指数分值 0–100")
    rating: str = Field(description="情绪标签，如 Extreme Fear / Fear / Neutral / Greed / Extreme Greed")


class FearGreedSnapshot(BaseResponse):
    """特定时间点的快照（当前/前一周/前一月/前一年/历史极值）。"""

    score: float = Field(ge=0, le=100)
    rating: str
    date: Optional[str] = Field(None, description="仅当前值、历史最高/最低时携带")


class FearGreedResponse(BaseResponse):
    """GET /api/v1/fear-greed 完整响应。"""

    current: FearGreedSnapshot
    previous_week: FearGreedSnapshot
    previous_month: FearGreedSnapshot
    previous_year: FearGreedSnapshot
    history_low: FearGreedSnapshot
    history_high: FearGreedSnapshot
    history: List[FearGreedPoint]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_fear_greed_schema.py -v
```

预期：6 passed

- [ ] **Step 5: 提交**

```bash
git add app/schemas/fear_greed.py tests/test_fear_greed_schema.py
git commit -m "feat: add Fear & Greed Index Pydantic schemas"
```

---

### Task 2: Backend Cache

**Files:**
- Create: `app/cache/fear_greed_cache.py`

- [ ] **Step 1: 创建 `app/cache/fear_greed_cache.py`**

```python
"""Fear & Greed Index Redis 缓存操作。

key: fear_greed:history:1y
TTL: 3600 秒
"""
import json
from typing import Optional

from redis.asyncio import Redis

from app.core.logging import logger
from app.schemas.fear_greed import FearGreedResponse

FEAR_GREED_CACHE_KEY = "fear_greed:history:1y"
FEAR_GREED_TTL = 3600


async def get_fear_greed_cache(redis: Redis) -> Optional[FearGreedResponse]:
    """读取缓存，未命中或反序列化失败返回 None。"""
    raw = await redis.get(FEAR_GREED_CACHE_KEY)
    if raw is None:
        return None
    try:
        return FearGreedResponse(**json.loads(raw))
    except Exception as e:
        logger.warning("fear_greed_cache_deserialize_error", error=str(e))
        return None


async def set_fear_greed_cache(redis: Redis, data: FearGreedResponse) -> None:
    """将数据写入 Redis，TTL = 3600s。出错时记录日志，不抛出异常（保留现有缓存）。"""
    try:
        payload = json.dumps(data.model_dump(mode="json"), ensure_ascii=False)
        await redis.set(FEAR_GREED_CACHE_KEY, payload, ex=FEAR_GREED_TTL)
        logger.info("fear_greed_cache_set", ttl=FEAR_GREED_TTL)
    except Exception as e:
        logger.warning("fear_greed_cache_set_error", error=str(e))
```

- [ ] **Step 2: 提交**

```bash
git add app/cache/fear_greed_cache.py
git commit -m "feat: add Fear & Greed Index Redis cache operations"
```

---

### Task 3: Backend Service

**Files:**
- Create: `app/services/fear_greed.py`
- Test: `tests/test_fear_greed_service.py`

- [ ] **Step 1: 检查 httpx 是否已安装，若无则安装**

```bash
uv run python -c "import httpx; print(httpx.__version__)" 2>/dev/null || uv add httpx
```

- [ ] **Step 2: 编写 failing service 测试**

```python
# tests/test_fear_greed_service.py
"""Fear & Greed Service 单元测试（mock CNN API 响应）。"""
import time
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.fear_greed import FearGreedService, _normalize_rating, _score_to_rating


def test_normalize_rating_maps_all_variants():
    assert _normalize_rating("extreme fear") == "Extreme Fear"
    assert _normalize_rating("fear") == "Fear"
    assert _normalize_rating("neutral") == "Neutral"
    assert _normalize_rating("greed") == "Greed"
    assert _normalize_rating("extreme greed") == "Extreme Greed"
    assert _normalize_rating("Extreme Greed") == "Extreme Greed"


def test_score_to_rating_boundaries():
    assert _score_to_rating(0) == "Extreme Fear"
    assert _score_to_rating(24) == "Extreme Fear"
    assert _score_to_rating(25) == "Fear"
    assert _score_to_rating(44) == "Fear"
    assert _score_to_rating(45) == "Neutral"
    assert _score_to_rating(55) == "Neutral"
    assert _score_to_rating(56) == "Greed"
    assert _score_to_rating(75) == "Greed"
    assert _score_to_rating(76) == "Extreme Greed"
    assert _score_to_rating(100) == "Extreme Greed"


@pytest.mark.asyncio
async def test_get_history_returns_cached_data():
    """缓存命中时直接返回，不调用 CNN API。"""
    from app.schemas.fear_greed import FearGreedPoint, FearGreedResponse, FearGreedSnapshot

    mock_redis = AsyncMock()
    cached = FearGreedResponse(
        current=FearGreedSnapshot(score=72, rating="Greed", date="2026-05-06"),
        previous_week=FearGreedSnapshot(score=38, rating="Fear"),
        previous_month=FearGreedSnapshot(score=51, rating="Neutral"),
        previous_year=FearGreedSnapshot(score=52, rating="Neutral"),
        history_low=FearGreedSnapshot(score=2, rating="Extreme Fear", date="2022-10-12"),
        history_high=FearGreedSnapshot(score=97, rating="Extreme Greed", date="2021-11-09"),
        history=[FearGreedPoint(date="2025-05-06", score=38, rating="Fear")],
    )

    with patch("app.services.fear_greed.get_fear_greed_cache", new_callable=AsyncMock) as mock_cache:
        mock_cache.return_value = cached
        service = FearGreedService()
        result = await service.get_history(mock_redis)

    assert result.current.score == 72
    mock_cache.assert_called_once_with(mock_redis)


@pytest.mark.asyncio
async def test_get_history_fetches_from_cnn_on_cache_miss():
    """缓存未命中时调用 CNN API 并写入缓存。"""
    today = date.today()
    start_date = today - timedelta(days=365)
    ts_ms = int(time.mktime(start_date.timetuple())) * 1000

    cnn_payload = {
        "fear_and_greed": {
            "score": 72.1,
            "rating": "Greed",
            "timestamp": f"{today.isoformat()}T00:00:00",
            "previous_1_week": {"score": 38.0, "rating": "Fear"},
            "previous_1_month": {"score": 51.0, "rating": "Neutral"},
            "previous_1_year": {"score": 52.0, "rating": "Neutral"},
        },
        "fear_and_greed_historical": {
            "data": [{"x": ts_ms, "y": 38.0}]
        },
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = cnn_payload
    mock_response.raise_for_status = MagicMock()

    mock_redis = AsyncMock()

    with (
        patch("app.services.fear_greed.get_fear_greed_cache", new_callable=AsyncMock, return_value=None),
        patch("app.services.fear_greed.set_fear_greed_cache", new_callable=AsyncMock) as mock_set,
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        service = FearGreedService()
        result = await service.get_history(mock_redis)

    assert result.current.score == pytest.approx(72.1, abs=0.1)
    assert result.current.rating == "Greed"
    assert len(result.history) == 1
    mock_set.assert_called_once()
```

- [ ] **Step 3: 运行测试确认失败**

```bash
uv run pytest tests/test_fear_greed_service.py -v
```

预期：`FAILED` — `ModuleNotFoundError: No module named 'app.services.fear_greed'`

- [ ] **Step 4: 实现 `app/services/fear_greed.py`**

```python
"""Fear & Greed Index 数据获取与缓存服务。"""
from datetime import date, datetime, timedelta, timezone

import httpx
from redis.asyncio import Redis

from app.cache.fear_greed_cache import get_fear_greed_cache, set_fear_greed_cache
from app.core.logging import logger
from app.schemas.fear_greed import FearGreedPoint, FearGreedResponse, FearGreedSnapshot

_CNN_BASE = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; deepalpha-bot/1.0)",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
}

_RATING_MAP = {
    "extreme fear": "Extreme Fear",
    "fear": "Fear",
    "neutral": "Neutral",
    "greed": "Greed",
    "extreme greed": "Extreme Greed",
}


def _normalize_rating(raw: str) -> str:
    return _RATING_MAP.get(raw.lower(), raw.title())


def _score_to_rating(score: float) -> str:
    if score <= 24:
        return "Extreme Fear"
    if score <= 44:
        return "Fear"
    if score <= 55:
        return "Neutral"
    if score <= 75:
        return "Greed"
    return "Extreme Greed"


class FearGreedService:
    async def get_history(self, redis: Redis) -> FearGreedResponse:
        cached = await get_fear_greed_cache(redis)
        if cached is not None:
            logger.info("fear_greed_cache_hit")
            return cached

        logger.info("fear_greed_cache_miss")
        return await self._fetch_and_cache(redis)

    async def _fetch_and_cache(self, redis: Redis) -> FearGreedResponse:
        start_date = (date.today() - timedelta(days=365)).isoformat()
        url = f"{_CNN_BASE}/{start_date}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            raw = resp.json()

        data = self._parse(raw)
        await set_fear_greed_cache(redis, data)
        return data

    def _parse(self, raw: dict) -> FearGreedResponse:
        fg = raw["fear_and_greed"]
        historical = raw["fear_and_greed_historical"]["data"]

        history_points = []
        for item in historical:
            ts_ms = item["x"]
            score = float(item["y"])
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()
            rating_raw = item.get("rating", _score_to_rating(score))
            history_points.append(FearGreedPoint(
                date=dt.isoformat(),
                score=round(score, 1),
                rating=_normalize_rating(rating_raw),
            ))

        history_points.sort(key=lambda p: p.date)

        scores = [p.score for p in history_points]
        low_idx = scores.index(min(scores)) if scores else 0
        high_idx = scores.index(max(scores)) if scores else 0

        current_score = round(float(fg["score"]), 1)
        current_date = datetime.fromisoformat(fg["timestamp"].split("T")[0]).date().isoformat()

        return FearGreedResponse(
            current=FearGreedSnapshot(
                score=current_score,
                rating=_normalize_rating(fg.get("rating", _score_to_rating(current_score))),
                date=current_date,
            ),
            previous_week=FearGreedSnapshot(
                score=round(float(fg["previous_1_week"]["score"]), 1),
                rating=_normalize_rating(
                    fg["previous_1_week"].get("rating", _score_to_rating(fg["previous_1_week"]["score"]))
                ),
            ),
            previous_month=FearGreedSnapshot(
                score=round(float(fg["previous_1_month"]["score"]), 1),
                rating=_normalize_rating(
                    fg["previous_1_month"].get("rating", _score_to_rating(fg["previous_1_month"]["score"]))
                ),
            ),
            previous_year=FearGreedSnapshot(
                score=round(float(fg["previous_1_year"]["score"]), 1),
                rating=_normalize_rating(
                    fg["previous_1_year"].get("rating", _score_to_rating(fg["previous_1_year"]["score"]))
                ),
            ),
            history_low=FearGreedSnapshot(
                score=history_points[low_idx].score if history_points else 0.0,
                rating=history_points[low_idx].rating if history_points else "Extreme Fear",
                date=history_points[low_idx].date if history_points else None,
            ),
            history_high=FearGreedSnapshot(
                score=history_points[high_idx].score if history_points else 100.0,
                rating=history_points[high_idx].rating if history_points else "Extreme Greed",
                date=history_points[high_idx].date if history_points else None,
            ),
            history=history_points,
        )


fear_greed_service = FearGreedService()
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_fear_greed_service.py -v
```

预期：5 passed

- [ ] **Step 6: 提交**

```bash
git add app/services/fear_greed.py tests/test_fear_greed_service.py
git commit -m "feat: add FearGreedService with CNN API proxy and Redis caching"
```

---

### Task 4: Backend Router + 注册

**Files:**
- Create: `app/api/v1/fear_greed.py`
- Modify: `app/api/v1/api.py`

- [ ] **Step 1: 创建 `app/api/v1/fear_greed.py`**

```python
"""Fear & Greed Index API 端点。"""
from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.cache.client import get_redis
from app.core.logging import logger
from app.schemas.fear_greed import FearGreedResponse
from app.services.fear_greed import fear_greed_service

router = APIRouter()


@router.get("", response_model=FearGreedResponse)
async def get_fear_greed(redis: Redis = Depends(get_redis)) -> FearGreedResponse:
    """获取 Fear & Greed Index 最近 1 年历史数据及统计快照。"""
    logger.info("fear_greed_request")
    return await fear_greed_service.get_history(redis)
```

- [ ] **Step 2: 修改 `app/api/v1/api.py`，挂载 fear_greed router**

将文件完整内容替换为：

```python
"""API v1 router configuration."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chatbot import router as chatbot_router
from app.api.v1.etf import router as etf_router
from app.api.v1.fear_greed import router as fear_greed_router
from app.core.logging import logger

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
api_router.include_router(etf_router, prefix="/etf", tags=["etf"])
api_router.include_router(fear_greed_router, prefix="/fear-greed", tags=["fear-greed"])


@api_router.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.info("health_check_called")
    return {"status": "healthy", "version": "1.0.0"}


@api_router.get("/hello")
async def hello():
    return {"deepalpha-club-ai": True}
```

- [ ] **Step 3: ruff 代码检查**

```bash
uv run ruff check app/api/v1/fear_greed.py app/api/v1/api.py
```

预期：无报错

- [ ] **Step 4: 运行所有后端测试**

```bash
uv run pytest tests/test_fear_greed_schema.py tests/test_fear_greed_service.py -v
```

预期：11 passed

- [ ] **Step 5: 提交**

```bash
git add app/api/v1/fear_greed.py app/api/v1/api.py
git commit -m "feat: register Fear & Greed router at /api/v1/fear-greed"
```

---

### Task 5: 前端 TypeScript 类型 + API 层

**Files:**
- Create: `frontend/lib/api/fear_greed.ts`

- [ ] **Step 1: 创建 `frontend/lib/api/fear_greed.ts`**

```typescript
import apiClient from './client'

export interface FearGreedPoint {
  date: string
  score: number
  rating: string
}

export interface FearGreedSnapshot {
  score: number
  rating: string
  date?: string
}

export interface FearGreedResponse {
  request_id: string
  current: FearGreedSnapshot
  previous_week: FearGreedSnapshot
  previous_month: FearGreedSnapshot
  previous_year: FearGreedSnapshot
  history_low: FearGreedSnapshot
  history_high: FearGreedSnapshot
  history: FearGreedPoint[]
}

export async function fetchFearGreed(): Promise<FearGreedResponse> {
  const { data } = await apiClient.get<FearGreedResponse>('/fear-greed')
  return data
}
```

- [ ] **Step 2: TypeScript 类型检查**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

预期：无新增报错

- [ ] **Step 3: 提交**

```bash
git add frontend/lib/api/fear_greed.ts
git commit -m "feat: add Fear & Greed Index Axios API client and TypeScript types"
```

---

### Task 6: Zustand Store

**Files:**
- Create: `frontend/lib/store/fear_greed.ts`

- [ ] **Step 1: 创建 `frontend/lib/store/fear_greed.ts`**

```typescript
import { create } from 'zustand'
import { fetchFearGreed, FearGreedResponse } from '@/lib/api/fear_greed'

interface FearGreedState {
  data: FearGreedResponse | null
  loading: boolean
  error: string | null
  fetchData: () => Promise<void>
}

export const useFearGreedStore = create<FearGreedState>((set) => ({
  data: null,
  loading: false,
  error: null,
  fetchData: async () => {
    set({ loading: true, error: null })
    try {
      const data = await fetchFearGreed()
      set({ data, loading: false })
    } catch (err) {
      const message = err instanceof Error ? err.message : '数据加载失败'
      set({ error: message, loading: false })
    }
  },
}))
```

- [ ] **Step 2: TypeScript 类型检查**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

预期：无新增报错

- [ ] **Step 3: 提交**

```bash
git add frontend/lib/store/fear_greed.ts
git commit -m "feat: add Fear & Greed Index Zustand store"
```

---

### Task 7: FearGreedChart 组件

**Files:**
- Create: `frontend/components/fear_greed/FearGreedChart.tsx`

- [ ] **Step 1: 创建组件目录**

```bash
mkdir -p frontend/components/fear_greed
```

- [ ] **Step 2: 创建 `frontend/components/fear_greed/FearGreedChart.tsx`**

```tsx
'use client'

import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  ColorType,
  LineSeries,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  LineData,
} from 'lightweight-charts'
import { FearGreedPoint, FearGreedSnapshot } from '@/lib/api/fear_greed'

interface Props {
  history: FearGreedPoint[]
  current: FearGreedSnapshot
}

const RATING_COLOR: Record<string, string> = {
  'Extreme Greed': '#16a34a',
  'Greed': '#4ade80',
  'Neutral': '#ca8a04',
  'Fear': '#f87171',
  'Extreme Fear': '#ef4444',
}

const RATING_LABEL: Record<string, string> = {
  'Extreme Greed': '极度贪婪',
  'Greed': '贪婪',
  'Neutral': '中性',
  'Fear': '恐惧',
  'Extreme Fear': '极度恐惧',
}

function getColor(rating: string): string {
  return RATING_COLOR[rating] ?? '#3b82f6'
}

export default function FearGreedChart({ history, current }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const [tooltip, setTooltip] = useState<{
    visible: boolean
    x: number
    y: number
    date: string
    score: number
    rating: string
  }>({ visible: false, x: 0, y: 0, date: '', score: 0, rating: '' })

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 340,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#374151',
      },
      grid: {
        vertLines: { color: 'rgba(156,163,175,0.15)' },
        horzLines: { color: 'rgba(156,163,175,0.15)' },
      },
      crosshair: { mode: CrosshairMode.Magnet },
      rightPriceScale: { borderColor: 'rgba(156,163,175,0.3)' },
      timeScale: {
        borderColor: 'rgba(156,163,175,0.3)',
        timeVisible: false,
      },
    })
    chartRef.current = chart

    const lineSeries = chart.addSeries(LineSeries, {
      color: getColor(current.rating),
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 5,
    })
    seriesRef.current = lineSeries

    // 锁定 Y 轴范围 0–100，使情绪色带位置准确
    lineSeries.applyOptions({
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: 0, maxValue: 100 },
        margins: { above: 2, below: 2 },
      }),
    })

    const chartData: LineData[] = history.map((p) => ({
      time: p.date as `${number}-${number}-${number}`,
      value: p.score,
    }))
    lineSeries.setData(chartData)
    chart.timeScale().fitContent()

    // Crosshair tooltip
    const ratingByDate = Object.fromEntries(history.map((p) => [p.date, p.rating]))
    chart.subscribeCrosshairMove((param) => {
      if (!param.point || !param.time || !containerRef.current) {
        setTooltip((t) => ({ ...t, visible: false }))
        return
      }
      const seriesData = param.seriesData.get(lineSeries)
      if (!seriesData || !('value' in seriesData)) {
        setTooltip((t) => ({ ...t, visible: false }))
        return
      }
      const dateStr = String(param.time)
      const score = (seriesData as LineData).value
      const rating = ratingByDate[dateStr] ?? ''
      const rect = containerRef.current.getBoundingClientRect()
      const x = param.point.x
      const y = param.point.y
      const tooltipWidth = 160
      const adjustedX = x + tooltipWidth > rect.width ? x - tooltipWidth - 10 : x + 10
      setTooltip({ visible: true, x: adjustedX, y: Math.max(0, y - 60), date: dateStr, score, rating })
    })

    // Resize observer
    const observer = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    })
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [history, current.rating])

  const currentColor = getColor(current.rating)

  return (
    <div className="relative">
      {/* 情绪色带背景（Y 轴锁定 0-100，色带按分值比例定位） */}
      <div
        className="absolute inset-0 pointer-events-none rounded-lg overflow-hidden"
        aria-hidden
      >
        <div
          className="w-full h-full"
          style={{
            background: [
              'linear-gradient(to bottom,',
              'rgba(22,163,74,0.08) 0%,',
              'rgba(22,163,74,0.08) 24%,',
              'rgba(74,222,128,0.08) 24%,',
              'rgba(74,222,128,0.08) 44%,',
              'rgba(202,138,4,0.08) 44%,',
              'rgba(202,138,4,0.08) 55%,',
              'rgba(248,113,113,0.08) 55%,',
              'rgba(248,113,113,0.08) 75%,',
              'rgba(239,68,68,0.10) 75%,',
              'rgba(239,68,68,0.10) 100%)',
            ].join(' '),
          }}
        />
      </div>

      {/* 图表容器 */}
      <div ref={containerRef} className="relative" style={{ height: 340 }} />

      {/* 当前值叠加显示（左上角） */}
      <div className="absolute top-3 left-4 pointer-events-none">
        <div className="text-4xl font-bold" style={{ color: currentColor }}>
          {Math.round(current.score)}
        </div>
        <div className="text-sm font-medium mt-0.5" style={{ color: currentColor }}>
          {RATING_LABEL[current.rating] ?? current.rating}
        </div>
      </div>

      {/* Crosshair Tooltip */}
      {tooltip.visible && (
        <div
          className="absolute pointer-events-none bg-white border border-gray-200 rounded-lg shadow-lg px-3 py-2 text-xs z-10"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <div className="text-gray-500 mb-1">{tooltip.date}</div>
          <div className="font-bold text-base" style={{ color: getColor(tooltip.rating) }}>
            {Math.round(tooltip.score)}
          </div>
          <div className="font-medium" style={{ color: getColor(tooltip.rating) }}>
            {RATING_LABEL[tooltip.rating] ?? tooltip.rating}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: TypeScript 类型检查**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

预期：无新增报错

- [ ] **Step 4: 提交**

```bash
git add frontend/components/fear_greed/FearGreedChart.tsx
git commit -m "feat: add FearGreedChart component with lightweight-charts v5 and emotion bands"
```

---

### Task 8: 前端页面 + 导航

**Files:**
- Create: `frontend/app/(dashboard)/fear-greed/page.tsx`
- Modify: `frontend/components/layout/TopNav.tsx`

- [ ] **Step 1: 创建页面目录**

```bash
mkdir -p "frontend/app/(dashboard)/fear-greed"
```

- [ ] **Step 2: 创建 `frontend/app/(dashboard)/fear-greed/page.tsx`**

```tsx
'use client'

import { useEffect } from 'react'
import { useFearGreedStore } from '@/lib/store/fear_greed'
import FearGreedChart from '@/components/fear_greed/FearGreedChart'
import { FearGreedSnapshot } from '@/lib/api/fear_greed'

const RATING_LABEL: Record<string, string> = {
  'Extreme Greed': '极度贪婪',
  'Greed': '贪婪',
  'Neutral': '中性',
  'Fear': '恐惧',
  'Extreme Fear': '极度恐惧',
}

const RATING_COLOR: Record<string, string> = {
  'Extreme Greed': '#16a34a',
  'Greed': '#4ade80',
  'Neutral': '#ca8a04',
  'Fear': '#f87171',
  'Extreme Fear': '#ef4444',
}

interface StatCardProps {
  label: string
  snapshot: FearGreedSnapshot
}

function StatCard({ label, snapshot }: StatCardProps) {
  const color = RATING_COLOR[snapshot.rating] ?? '#6b7280'
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col gap-1">
      <div className="text-xs text-gray-500 font-medium">{label}</div>
      <div className="text-2xl font-bold" style={{ color }}>
        {Math.round(snapshot.score)}
      </div>
      <div className="text-xs font-medium" style={{ color }}>
        {RATING_LABEL[snapshot.rating] ?? snapshot.rating}
      </div>
      {snapshot.date && (
        <div className="text-xs text-gray-400 mt-0.5">{snapshot.date}</div>
      )}
    </div>
  )
}

export default function FearGreedPage() {
  const { data, loading, error, fetchData } = useFearGreedStore()

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* 页头 */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">恐慌与贪婪指数</h1>
          <p className="text-sm text-gray-500 mt-1">
            数据来源：CNN Fear &amp; Greed Index · 每小时更新
          </p>
        </div>

        {/* 图表卡片 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          {loading && (
            <div className="flex items-center justify-center h-[340px] text-gray-400 text-sm">
              加载中...
            </div>
          )}
          {error && !loading && (
            <div className="flex items-center justify-center h-[340px] text-red-500 text-sm">
              {error}
            </div>
          )}
          {data && !loading && (
            <FearGreedChart history={data.history} current={data.current} />
          )}
        </div>

        {/* 统计卡片行 */}
        {data && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <StatCard label="前一周" snapshot={data.previous_week} />
            <StatCard label="前一月" snapshot={data.previous_month} />
            <StatCard label="前一年" snapshot={data.previous_year} />
            <StatCard label="历史最低" snapshot={data.history_low} />
            <StatCard label="历史最高" snapshot={data.history_high} />
            <StatCard label="今日" snapshot={data.current} />
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 修改 `frontend/components/layout/TopNav.tsx`，插入恐慌指数导航项**

将 `NAV_ITEMS` 替换为（在 ETF 前插入）：

```typescript
const NAV_ITEMS = [
  { href: '/dashboard', label: '仪表盘' },
  { href: '/fear-greed', label: '恐慌指数' },
  { href: '/etf', label: 'ETF 资金流' },
  { href: '/chat', label: 'AI 对话' },
  { href: '/settings', label: '设置' },
] as const
```

- [ ] **Step 4: TypeScript 类型检查**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

预期：无新增报错

- [ ] **Step 5: 运行所有后端测试**

```bash
cd /Users/hanqing.zf/PycharmProjects/deepalpha-club-ai
uv run pytest tests/test_fear_greed_schema.py tests/test_fear_greed_service.py -v
```

预期：11 passed

- [ ] **Step 6: 提交**

```bash
git add "frontend/app/(dashboard)/fear-greed/page.tsx" \
        frontend/components/layout/TopNav.tsx
git commit -m "feat: add Fear & Greed Index page and navigation item"
```
