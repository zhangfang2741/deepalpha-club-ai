# 结构性投资六层评分系统设计

> 日期：2026-05-10
> 状态：草稿
> 作者：Claude

---

## 一、目标和范围

**目标用户**：个人投资者

**核心功能**：
1. 股票评分卡片 — 输入股票代码，生成六层评分报告
2. 雷达图对比 — 同时对比 2-3 只股票的各维度得分
3. 选股列表 — 按行业/评分筛选股票，按综合评分排序
4. 综合研报视图 — 生成图文混排的投资分析报告

**MVP 优先级**：全六层都做，每层用最简免费数据源

---

## 二、数据源设计

### 2.1 数据源矩阵

| 层级 | 数据类型 | 数据源 | 免费限制 |
|------|---------|--------|---------|
| 行业层 | 行业分类、板块趋势 | yfinance (sector/industry) | 无限制 |
| 公司层 | 基本信息、商业模式、护城河 | yfinance + 公开信息 | 无限制 |
| 财务层 | 营收、利润、现金流、财务比率 | yfinance (financials) | 无限制 |
| 竞争格局层 | 市占率、同行对比 | yfinance (competitors) + 计算 | 无限制 |
| 交易结构层 | 估值指标、市场情绪 | yfinance (info) + Fear & Greed | 无限制 |
| 预期差层 | 新闻情绪、分析师预期 | NewsAPI free tier | 100req/day |

### 2.2 数据抽象层

```python
# app/services/scoring/data_sources/
class DataSourceInterface:
    """数据源统一接口"""
    async def get_industry_data(symbol: str) -> IndustryData
    async def get_company_data(symbol: str) -> CompanyData
    async def get_financial_data(symbol: str) -> FinancialData
    async def get_competition_data(symbol: str) -> CompetitionData
    async def get_trading_data(symbol: str) -> TradingData
    async def get_expectation_data(symbol: str) -> ExpectationData
```

### 2.3 缓存策略

| 数据类型 | TTL | 缓存键格式 | 刷新策略 |
|---------|-----|-----------|---------|
| 股票基本信息 | 24h | `stock:info:{symbol}` | 定时过期 |
| 财务数据 | 6h | `stock:financial:{symbol}` | 财报发布后刷新 |
| 价格/估值 | 5min | `stock:price:{symbol}` | 频繁访问时刷新 |
| 行业数据 | 1h | `stock:industry:{symbol}` | 批量更新 |
| 新闻情绪 | 15min | `stock:news:{symbol}` | 按需刷新 |

**频率控制**：
- yfinance：无限制，不做额外控制
- NewsAPI：每日请求计数，余额不足时降级到缓存数据
- 所有外部调用记录日志，便于监控

---

## 三、后端设计

### 3.1 API 端点

```
GET  /api/v1/scoring/stock/{symbol}
     → 返回股票六层评分卡片

POST /api/v1/scoring/compare
     body: {"symbols": ["AAPL", "MSFT"]}
     → 返回雷达图对比数据

GET  /api/v1/scoring/list
     query: ?industry=Technology&min_score=70
     → 返回符合筛选条件的股票列表

GET  /api/v1/scoring/report/{symbol}
     → 返回综合研报视图数据
```

### 3.2 服务结构

```
app/services/scoring/
├── __init__.py
├── data_sources/          # 数据抽象层
│   ├── __init__.py
│   ├── base.py           # DataSourceInterface
│   ├── yfinance_source.py
│   └── newsapi_source.py
├── scorers/              # 各层评分器
│   ├── __init__.py
│   ├── industry_scorer.py
│   ├── company_scorer.py
│   ├── financial_scorer.py
│   ├── competition_scorer.py
│   ├── trading_scorer.py
│   └── expectation_scorer.py
├── aggregator.py        # 权重计算 + 综合评分
└── cache.py             # 评分结果缓存
```

### 3.3 评分算法

**权重分配**：
| 层级 | 权重 |
|------|-----|
| 行业层 | 20% |
| 公司层 | 20% |
| 财务层 | 20% |
| 竞争格局层 | 15% |
| 交易结构层 | 15% |
| 预期差层 | 10% |

**评分范围**：0-100，保留整数

**各层评分逻辑**：

1. **行业层**：基于行业增长性、周期性、长期驱动力
2. **公司层**：基于商业模式、护城河、企业生态位
3. **财务层**：基于营收增长、利润率、现金流、Rule of 40
4. **竞争格局层**：基于市占率、增速对比、技术壁垒
5. **交易结构层**：基于 PE/P/S 估值分位、市场情绪
6. **预期差层**：基于新闻情绪偏离度、分析师预期差

---

## 四、前端设计

### 4.1 页面结构

```
frontend/app/(dashboard)/
├── scoring/                    # 新 Tab 页面
│   ├── page.tsx              # 主页面（Tab 容器）
│   ├── components/
│   │   ├── ScoringTabs.tsx   # 子 Tab 切换
│   │   ├── StockCard.tsx     # 股票评分卡片
│   │   ├── RadarChart.tsx     # 雷达图组件
│   │   ├── StockList.tsx     # 选股列表
│   │   └── ReportView.tsx    # 研报视图
│   └── lib/
│       └── scoring.ts        # API 调用封装
```

### 4.2 导航设计

在现有导航栏添加 "投资评分" 入口：

```
导航栏: 首页 | ETF | Fear & Greed | 投资评分 | ...
```

### 4.3 组件设计

**股票评分卡片**：
- 顶部：股票代码、名称、当前价格
- 中部：六层评分条形图 + 综合评分
- 底部：关键指标摘要

**雷达图对比**：
- 支持 2-3 只股票同时对比
- 统一坐标轴，便于直观比较
- 点击股票名称切换显示/隐藏

**选股列表**：
- 左侧筛选器：行业、评分区间、交易所
- 右侧列表：股票卡片，含综合评分和关键指标

**研报视图**：
- 类似研报的排版，包含各层分析详情
- 支持导出（可选，MVP 阶段简化）

### 4.4 状态管理

使用 Zustand 管理评分相关状态：

```typescript
// frontend/lib/store/scoring.ts
interface ScoringState {
  currentStock: string | null;
  scores: LayerScores | null;
  compareStocks: string[];
  compareScores: Map<string, LayerScores>;
  filters: FilterOptions;
  loading: boolean;
}
```

---

## 五、实现计划

### Phase 1: 数据层 + 评分核心
- 实现数据抽象层
- 实现各层评分器
- 实现权重聚合
- 单元测试

### Phase 2: API 层
- 实现评分 API 端点
- 实现缓存逻辑
- API 文档

### Phase 3: 前端页面
- 创建投资评分 Tab 页面
- 实现股票评分卡片
- 实现雷达图对比
- 实现选股列表（MVP 简化版）
- 研报视图（后续迭代）

### Phase 4: 优化
- 缓存优化
- 错误处理
- 性能优化

---

## 六、数据流

```
用户输入股票代码
        ↓
前端调用 /api/v1/scoring/stock/{symbol}
        ↓
检查 Redis 缓存
        ↓
┌─ 命中 ──→ 返回缓存数据
│
└─ 未命中 ─→ DataSource 获取数据
                 ↓
           各层评分器计算得分
                 ↓
           权重聚合 → 综合评分
                 ↓
           存入 Redis (分 TTL)
                 ↓
           返回评分结果
```

---

## 七、TODO

- [ ] 数据抽象层实现
- [ ] 六层评分器实现
- [ ] 缓存层实现
- [ ] API 端点实现
- [ ] 前端 Tab 页面
- [ ] 评分卡片组件
- [ ] 雷达图组件
- [ ] 选股列表
- [ ] 研报视图（后续）
- [ ] 集成测试

---

## 八、风险和备选

| 风险 | 应对 |
|------|-----|
| NewsAPI 免费额度过低 | 降级到只使用缓存数据 + yfinance |
| yfinance 数据不稳定 | 添加重试 + 降级到静态数据 |
| 评分算法需要调优 | MVP 使用简单规则，后续迭代优化 |
| 前端性能问题 | 分页/懒加载 + 缓存 |

---

## 九、验收标准

1. 输入股票代码，返回六层评分
2. 支持 2-3 只股票雷达图对比
3. 选股列表可按行业/评分筛选
4. 所有 API 响应 < 2s（缓存命中）
5. 视觉风格与现有页面一致
6. 无价格的数据使用占位符，不报错