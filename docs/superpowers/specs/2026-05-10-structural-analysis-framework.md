# 结构性投资六层分析框架 - 技术规格

> 基于 `idea/结构性投资六层分析框架.md` 的实现计划
> 测试股票: NVDA | 数据保留: 2-3年

---

## 1. 概述

### 1.1 目标
构建一个自动化的美股投资分析系统，从"行业→公司→财务→竞争格局→交易结构→预期差"六层结构进行综合分析，所有数据来源可溯。

### 1.2 核心原则
- **数据可靠**: 所有喂给 AI 的数据必须携带来源、URL、时间戳
- **自动抓取**: 财务数据自动从 SEC EDGAR/FMP 获取
- **异步分析**: 后台任务 + SSE 实时推送
- **可回溯**: 支持 2-3 年历史快照查询

---

## 2. 系统架构

### 2.1 六层分析流程

```
┌─────────────────────────────────────────────────────────────┐
│                      用户请求 (NVDA)                        │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    并行数据抓取层                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Industry │  │Financial │  │   News  │  │ Trading  │   │
│  │  Agent   │  │  Agent   │  │  Agent  │  │  Agent   │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
└───────┼─────────────┼─────────────┼─────────────┼──────────┘
        │             │             │             │
        └────────────┴─────────────┴─────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      综合分析层                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  AI Synthesizer: 六层评分 + 投资建议 + 预期差分析     │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      报告输出层                             │
│  - 六层评分雷达图                                           │
│  - 数据来源面板 (可点击溯源)                                │
│  - 异步 SSE 推送                                            │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 数据源矩阵

| 层级 | 数据类型 | 数据源 | 优先级 |
|------|---------|--------|--------|
| 行业层 | 行业趋势、赛道分类 | BLS、行业协会报告 | P1 |
| 公司层 | 商业模式、竞争对手 | Crunchbase、Wikipedia | P1 |
| 财务层 | 营收、利润、现金流 | **SEC EDGAR** + FMP | P0 |
| 竞争层 | 市占率、竞品对比 | Crunchbase、SEC 10-K | P2 |
| 交易层 | 估值、机构持仓 | FMP、WhaleWisdom | P1 |
| 情绪层 | 新闻、情绪指标 | NewsAPI + Fear&Greed | P1 |

---

## 3. 数据模型

### 3.1 DataPoint - 可溯源数据点

```python
class DataPoint(BaseModel):
    """每个分析数据必须携带来源信息"""
    value: Any                      # 数据值
    label: str                      # 数据标签 "Revenue 2024"
    source: str                     # "SEC EDGAR", "FMP", "CNN"
    url: Optional[str]              # 可点击溯源链接
    fetched_at: datetime            # 抓取时间
```

### 3.2 LayerAnalysis - 单层分析结果

```python
class LayerAnalysis(BaseModel):
    """单个分析层的结果"""
    layer_name: str                 # "industry", "financial", etc.
    score: float                    # 0-100 评分
    summary: str                    # 文字总结
    key_findings: List[str]         # 关键发现
    data_points: List[DataPoint]     # 支撑数据
```

### 3.3 AnalysisReport - 最终报告

```python
class AnalysisReport(BaseModel):
    """完整分析报告"""
    ticker: str
    company_name: str
    generated_at: datetime
    layers: Dict[str, LayerAnalysis]
    final_score: float              # 综合评分 0-100
    recommendation: str             # "BUY", "HOLD", "SELL"
    risk_reward_ratio: float         # 风险收益比
    sources: List[DataPoint]        # 所有引用的数据源
```

---

## 4. API 设计

### 4.1 创建分析任务

```
POST /api/v1/analysis
```

Request:
```json
{
  "ticker": "NVDA",
  "layers": ["industry", "financial", "news", "trading"],
  "as_of_date": "2024-01-15"  // 可选，用于时间回拨
}
```

Response:
```json
{
  "task_id": "uuid",
  "status": "queued",
  "created_at": "2024-01-15T10:00:00Z"
}
```

### 4.2 查询任务状态

```
GET /api/v1/analysis/{task_id}
```

Response:
```json
{
  "task_id": "uuid",
  "status": "completed",  // "queued", "processing", "completed", "failed"
  "progress": {
    "industry": "completed",
    "financial": "completed",
    "news": "processing",
    "trading": "pending"
  },
  "result": { ... }  // 仅当 completed 时
}
```

### 4.3 SSE 实时推送

```
GET /api/v1/analysis/{task_id}/stream
```

Events:
```
event: progress
data: {"layer": "financial", "status": "completed", "score": 85}

event: progress
data: {"layer": "news", "status": "completed", "score": 72}

event: completed
data: {"report": {...}}
```

---

## 5. 实现计划

### Phase 1: 数据层 (1-2周)
- [ ] `app/services/analyzer/sources.py` - DataPoint 模型
- [ ] `app/services/analyzer/sec_edgar.py` - SEC 财报抓取
- [ ] `app/services/analyzer/fmp_client.py` - FMP 财务数据
- [ ] `app/services/analyzer/news_client.py` - 新闻聚合

### Phase 2: Agent 层 (1-2周)
- [ ] 扩展 `app/schemas/graph.py` - AnalysisState
- [ ] 新建 `app/core/langgraph/tools/analyze_stock.py`
- [ ] 实现六层并行分析工作流

### Phase 3: API 层 (1周)
- [ ] `app/api/v1/analysis.py` - 分析端点
- [ ] SSE 实时推送
- [ ] 任务队列集成

### Phase 4: 存储层 (1周)
- [ ] `app/models/analysis.py` - 分析报告模型
- [ ] 历史快照存储
- [ ] 2-3年数据保留策略

---

## 6. 依赖项

### Python 依赖
- `sec-edgar-api`: SEC EDGAR 文件抓取
- `fmp-python`: Financial Modeling Prep API
- `newsapi-python`: 新闻数据
- `beautifulsoup4`: HTML 解析
- `lxml`: XML 解析 (用于 XBRL)

### 已有依赖复用
- ✅ `yfinance`: K线/价格数据 (已在 app/services/etf/fetcher.py 使用)
- ✅ `httpx`: HTTP 客户端
- ✅ Redis: 缓存层

---

## 7. 测试用例

### 7.1 NVDA 完整分析测试
```python
def test_nvda_full_analysis():
    # 1. 创建分析任务
    response = client.post("/api/v1/analysis", json={"ticker": "NVDA"})
    task_id = response.json()["task_id"]
    
    # 2. 等待完成
    result = wait_for_completion(task_id)
    
    # 3. 验证结果
    assert result.final_score > 0
    assert len(result.layers) == 6
    assert all(dp.source for dp in result.sources)
```

---

## 8. 风险与缓解

| 风险 | 缓解策略 |
|------|---------|
| SEC API 限流 | 添加请求延迟 + Redis 缓存 |
| 数据延迟 | 标注数据时效性警告 |
| AI 幻觉 | 强制 Source Attribution |
| 长时间任务 | 实现超时 + 部分结果返回 |