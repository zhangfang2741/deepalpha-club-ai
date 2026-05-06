# Fear & Greed Index 页面设计文档

**日期：** 2026-05-06  
**状态：** 已批准，待实施

---

## 概述

在现有仪表盘中新增「恐慌与贪婪指数」页面，路由为 `/fear-greed`，导航位置在 ETF 资金流之前。数据来源为 CNN Markets Fear & Greed Index，通过后端代理获取并缓存，前端展示带情绪色带的折线图及历史统计卡片。

---

## 功能需求

- 展示最近 1 年的 Fear & Greed 历史走势折线图（固定范围，无时间选择器）
- 折线图背景按情绪区间染色（极度恐惧 / 恐惧 / 中性 / 贪婪 / 极度贪婪）
- 图表支持鼠标悬停 tooltip，显示具体日期、数值、情绪标签
- 底部 6 张统计卡片：前一周、前一月、前一年、历史最低、历史最高、当前今日

---

## 情绪区间定义

| 分值范围 | 情绪标签 | 颜色 |
|---------|---------|------|
| 76–100 | 极度贪婪 (Extreme Greed) | `#16a34a` 深绿 |
| 56–75  | 贪婪 (Greed)             | `#4ade80` 浅绿 |
| 45–55  | 中性 (Neutral)           | `#ca8a04` 黄色 |
| 25–44  | 恐惧 (Fear)              | `#f87171` 浅红 |
| 0–24   | 极度恐惧 (Extreme Fear)   | `#ef4444` 深红 |

---

## 架构与数据流

```
CNN API (production.dataviz.cnn.io)
        ↓ 后端代理（检查 Redis 缓存）
FastAPI  GET /api/v1/fear-greed
        ↓ 缓存未命中时请求，结果存 Redis TTL=3600s
Redis   key: fear_greed:history:1y
        ↓
前端 Axios (lib/api/client.ts) → lib/api/fear_greed.ts
        ↓
Zustand useFearGreedStore (lib/store/fear_greed.ts)
        ↓
/fear-greed 页面 → FearGreedChart 组件 (lightweight-charts LineSeries)
```

**CNN API 端点：**
`https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start_date}`

start_date 为今日减 365 天，格式 `YYYY-MM-DD`。

---

## 后端设计

### 新增文件

**`app/services/fear_greed.py`**

```python
class FearGreedService:
    async def get_history(self, redis) -> dict:
        # 1. 检查 Redis key: fear_greed:history:1y
        # 2. 命中 → 反序列化并返回
        # 3. 未命中 → 调用 CNN API（start_date = today - 365d）
        # 4. 解析数据，计算统计值
        # 5. 写入 Redis，TTL = 3600s
        # 6. 返回结构化数据
```

**`app/api/v1/fear_greed.py`**

```python
router = APIRouter(prefix="/fear-greed", tags=["fear-greed"])

@router.get("")
async def get_fear_greed(redis=Depends(get_redis)) -> FearGreedResponse:
    return await fear_greed_service.get_history(redis)
```

### 响应结构

```json
{
  "current":       { "score": 72, "rating": "Greed",        "date": "2026-05-06" },
  "previous_week": { "score": 38, "rating": "Fear" },
  "previous_month":{ "score": 51, "rating": "Neutral" },
  "previous_year": { "score": 52, "rating": "Neutral" },
  "history_low":   { "score": 2,  "rating": "Extreme Fear", "date": "2022-10-12" },
  "history_high":  { "score": 97, "rating": "Extreme Greed","date": "2021-11-09" },
  "history": [
    { "date": "2025-05-06", "score": 38, "rating": "Fear" },
    ...
  ]
}
```

### 修改文件

- `app/main.py` 或 `app/api/v1/__init__.py`：挂载 `fear_greed.router`

---

## 前端设计

### 新增文件

| 文件 | 说明 |
|------|------|
| `frontend/lib/api/fear_greed.ts` | Axios API 层，调用 `/api/v1/fear-greed` |
| `frontend/lib/store/fear_greed.ts` | Zustand store，管理数据和加载状态 |
| `frontend/app/(dashboard)/fear-greed/page.tsx` | 页面（use client，含加载/错误状态） |
| `frontend/components/fear_greed/FearGreedChart.tsx` | lightweight-charts LineSeries 图表组件 |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `frontend/components/layout/TopNav.tsx` | 在 ETF 前插入 `{ href: '/fear-greed', label: '恐慌指数' }` |

### 组件结构

```
page.tsx
├── 页面标题 + 副标题（数据来源说明）
├── FearGreedChart.tsx
│   ├── 当前值大字 + 情绪标签（绝对定位叠加）
│   ├── lightweight-charts 图表（LineSeries + 色带背景 Band 或 Pane）
│   └── X 轴日期标签
└── 统计卡片行（6 个）
    ├── 前一周
    ├── 前一月
    ├── 前一年
    ├── 历史最低
    ├── 历史最高
    └── 当前今日
```

### 图表实现要点

- 使用 `lightweight-charts` v5 的 `createChart` + `addLineSeries`
- 情绪色带用 `addLineSeries` 的 `topColor` / `bottomColor` 模拟，或在图表 DOM 层叠 SVG 色带
- Tooltip 通过 `chart.subscribeCrosshairMove` 实现自定义悬停提示
- 颜色随情绪区间动态变化（折线颜色跟随当前值的区间色）

### 状态管理（Zustand Store）

```typescript
interface FearGreedState {
  data: FearGreedResponse | null
  loading: boolean
  error: string | null
  fetchData: () => Promise<void>
}
```

---

## UI 风格规范

遵循现有设计系统：

- 卡片：`bg-white rounded-xl border border-gray-200`
- 页面背景：`bg-gray-50`
- 主色调：蓝色折线 `#3b82f6`
- 统计卡片情绪颜色：按情绪区间映射（绿/黄/红）
- 字体：Geist Sans（与全局一致）

---

## 约束与风险

1. **CNN API 稳定性**：`production.dataviz.cnn.io` 是非公开接口，有被封或结构变更风险。后端应做异常处理，返回友好错误信息。
2. **CORS**：CNN API 仅允许后端请求，前端不可直连。
3. **缓存穿透**：CNN API 报错时不覆盖现有缓存，保留上次有效数据。
