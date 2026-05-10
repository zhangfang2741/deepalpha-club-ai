# 结构性投资六层评分系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建六层股票评分系统，包括后端评分服务和前端评分页面

**Architecture:**
- 后端：数据抽象层 + 六层评分器 + 权重聚合，通过 FastAPI 提供 REST API
- 前端：投资评分 Tab 页面，包含评分卡片、雷达图对比、选股列表
- 数据源：yfinance（免费无限制）+ NewsAPI（免费 100req/day）
- 缓存：Redis 按数据类型分层 TTL

**Tech Stack:** Python/FastAPI, TypeScript/Next.js, yfinance, zustand, recharts

---

## 文件结构

### 后端新增文件
```
app/
├── schemas/
│   └── scoring.py              # 评分相关的 Pydantic schemas
├── services/scoring/
│   ├── __init__.py
│   ├── data_sources/
│   │   ├── __init__.py
│   │   ├── base.py             # DataSourceInterface 抽象类
│   │   ├── yfinance_source.py  # yfinance 数据源实现
│   │   └── newsapi_source.py   # NewsAPI 数据源实现
│   ├── scorers/
│   │   ├── __init__.py
│   │   ├── industry.py         # 行业层评分
│   │   ├── company.py          # 公司层评分
│   │   ├── financial.py        # 财务层评分
│   │   ├── competition.py      # 竞争格局层评分
│   │   ├── trading.py          # 交易结构层评分
│   │   └── expectation.py      # 预期差层评分
│   ├── aggregator.py           # 权重聚合 + 综合评分
│   └── cache.py                # 评分缓存逻辑
├── api/v1/
│   └── scoring.py              # 评分 API 路由
```

### 前端新增文件
```
frontend/
├── app/(dashboard)/scoring/
│   ├── page.tsx                # 投资评分主页面（Tab 容器）
│   └── components/
│       ├── ScoringTabs.tsx     # 子 Tab 切换
│       ├── StockSearch.tsx     # 股票搜索输入
│       ├── ScoreCard.tsx       # 股票评分卡片
│       ├── RadarChart.tsx      # 雷达图组件
│       ├── StockList.tsx      # 选股列表
│       └── ReportView.tsx      # 研报视图（后续）
├── lib/api/
│   └── scoring.ts              # 评分 API 调用封装
├── lib/store/
│   └── scoring.ts              # 评分 Zustand store
```

### 前端修改文件
- `frontend/components/layout/TopNav.tsx` — 添加"投资评分"导航项

---

## 实现任务

### Task 1: 后端 schemas 和数据抽象层

**Files:**
- Create: `app/schemas/scoring.py`
- Create: `app/services/scoring/__init__.py`
- Create: `app/services/scoring/data_sources/__init__.py`
- Create: `app/services/scoring/data_sources/base.py`
- Create: `app/services/scoring/data_sources/yfinance_source.py`

- [ ] **Step 1: 创建评分相关 Pydantic schemas**

```python
# app/schemas/scoring.py
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import date

class LayerScore(BaseModel):
    """单层评分"""
    name: str  # 中文名称
    score: int  # 0-100
    weight: float  # 权重
    details: Dict[str, float] = {}  # 子指标详情

class StockScore(BaseModel):
    """股票完整评分"""
    symbol: str
    name: str
    current_price: Optional[float]
    sector: Optional[str]
    industry: Optional[str]
    layers: List[LayerScore]
    total_score: int  # 综合评分
    timestamp: date

class CompareRequest(BaseModel):
    symbols: List[str]  # 2-3 只股票

class CompareResponse(BaseModel):
    stocks: List[StockScore]

class StockListItem(BaseModel):
    """选股列表项"""
    symbol: str
    name: str
    sector: Optional[str]
    total_score: int
    price: Optional[float]
    change_pct: Optional[float]

class StockListResponse(BaseModel):
    items: List[StockListItem]
    total: int
```

- [ ] **Step 2: 创建数据源抽象接口**

```python
# app/services/scoring/data_sources/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class DataSourceInterface(ABC):
    """数据源统一接口"""

    @abstractmethod
    async def get_industry_data(self, symbol: str) -> Dict[str, Any]:
        """获取行业数据：行业名、板块、增长性"""
        pass

    @abstractmethod
    async def get_company_data(self, symbol: str) -> Dict[str, Any]:
        """获取公司数据：基本信息、商业模式、护城河"""
        pass

    @abstractmethod
    async def get_financial_data(self, symbol: str) -> Dict[str, Any]:
        """获取财务数据：营收、利润、现金流"""
        pass

    @abstractmethod
    async def get_competition_data(self, symbol: str) -> Dict[str, Any]:
        """获取竞争数据：市占率、同行对比"""
        pass

    @abstractmethod
    async def get_trading_data(self, symbol: str) -> Dict[str, Any]:
        """获取交易数据：估值、情绪"""
        pass

    @abstractmethod
    async def get_expectation_data(self, symbol: str) -> Dict[str, Any]:
        """获取预期数据：新闻情绪、分析师预期"""
        pass
```

- [ ] **Step 3: 创建 yfinance 数据源实现**

```python
# app/services/scoring/data_sources/yfinance_source.py
import yfinance as yf
from typing import Dict, Any
from .base import DataSourceInterface
from app.core.logging import logger

class YFinanceDataSource(DataSourceInterface):
    """Yahoo Finance 数据源"""

    async def get_industry_data(self, symbol: str) -> Dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            return {
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "long_name": info.get("longName", info.get("shortName")),
            }
        except Exception as e:
            logger.warning("yfinance_industry_failed", symbol=symbol, error=str(e))
            return {}

    async def get_company_data(self, symbol: str) -> Dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            return {
                "long_name": info.get("longName", info.get("shortName")),
                "business_summary": info.get("businessSummary"),
                "website": info.get("website"),
                "employee_count": info.get("fullTimeEmployees"),
                "ceo": info.get("ceo"),
            }
        except Exception as e:
            logger.warning("yfinance_company_failed", symbol=symbol, error=str(e))
            return {}

    async def get_financial_data(self, symbol: str) -> Dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            return {
                "revenue": info.get("totalRevenue"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "gross_margin": info.get("grossMargins"),
                "operating_margin": info.get("operatingMargins"),
                "profit_margin": info.get("profitMargins"),
                "fcf_margin": info.get("freeCashflow") / info.get("totalRevenue") if info.get("totalRevenue") else None,
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "price_to_sales": info.get("priceToSalesTrailing12Months"),
                "market_cap": info.get("marketCap"),
                "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            }
        except Exception as e:
            logger.warning("yfinance_financial_failed", symbol=symbol, error=str(e))
            return {}

    async def get_competition_data(self, symbol: str) -> Dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            return {
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
            }
        except Exception as e:
            logger.warning("yfinance_competition_failed", symbol=symbol, error=str(e))
            return {}

    async def get_trading_data(self, symbol: str) -> Dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            return {
                "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "avg_vol": info.get("averageVolume"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "price_to_sales": info.get("priceToSalesTrailing12Months"),
                "market_cap": info.get("marketCap"),
                "beta": info.get("beta"),
            }
        except Exception as e:
            logger.warning("yfinance_trading_failed", symbol=symbol, error=str(e))
            return {}

    async def get_expectation_data(self, symbol: str) -> Dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            return {
                "target_mean_price": info.get("targetMeanPrice"),
                "target_high_price": info.get("targetHighPrice"),
                "target_low_price": info.get("targetLowPrice"),
                "recommendation_key": info.get("recommendationKey"),  # buy/sell/hold
                "number_of_analyst_opinions": info.get("numberOfAnalystOpinions"),
            }
        except Exception as e:
            logger.warning("yfinance_expectation_failed", symbol=symbol, error=str(e))
            return {}
```

- [ ] **Step 4: 创建 NewsAPI 数据源（用于预期差层）**

```python
# app/services/scoring/data_sources/newsapi_source.py
import httpx
from typing import Dict, Any, List
from app.core.config import settings
from app.core.logging import logger

NEWSAPI_DAILY_LIMIT = 100

class NewsAPIDataSource:
    """NewsAPI 数据源（用于预期差层）"""

    def __init__(self):
        self.api_key = settings.NEWS_API_KEY
        self.base_url = "https://newsapi.org/v2"
        self._daily_count = 0
        self._reset_date = ""

    def _check_limit(self) -> bool:
        """检查是否超过每日限制"""
        import datetime
        today = datetime.date.today().isoformat()
        if self._reset_date != today:
            self._daily_count = 0
            self._reset_date = today
        return self._daily_count < NEWSAPI_DAILY_LIMIT

    async def get_news_sentiment(self, symbol: str) -> Dict[str, Any]:
        """获取新闻情绪数据"""
        if not self.api_key or not self._check_limit():
            logger.warning("newsapi_limit_reached", symbol=symbol)
            return {"sentiment": "unknown", "articles": [], "daily_count": self._daily_count}

        try:
            self._daily_count += 1
            url = f"{self.base_url}/everything"
            params = {
                "q": symbol,
                "apiKey": self.api_key,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 10,
            }
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()

            articles = data.get("articles", [])
            return {
                "total_results": data.get("totalResults", 0),
                "articles": [
                    {"title": a.get("title"), "published_at": a.get("publishedAt")}
                    for a in articles[:5]
                ],
                "daily_count": self._daily_count,
            }
        except Exception as e:
            logger.warning("newsapi_fetch_failed", symbol=symbol, error=str(e))
            return {"sentiment": "unknown", "articles": [], "daily_count": self._daily_count}
```

- [ ] **Step 5: 提交代码**

```bash
git add app/schemas/scoring.py app/services/scoring/ app/api/v1/scoring.py
git commit -m "feat: add scoring schemas and data abstraction layer"
```

---

### Task 2: 六层评分器实现

**Files:**
- Create: `app/services/scoring/scorers/__init__.py`
- Create: `app/services/scoring/scorers/industry.py`
- Create: `app/services/scoring/scorers/company.py`
- Create: `app/services/scoring/scorers/financial.py`
- Create: `app/services/scoring/scorers/competition.py`
- Create: `app/services/scoring/scorers/trading.py`
- Create: `app/services/scoring/scorers/expectation.py`

- [ ] **Step 1: 创建评分器基类和行业层评分**

```python
# app/services/scoring/scorers/base.py (内联到 industry.py)
from typing import Dict, Any, Optional

class Scorer:
    """评分器基类"""
    name: str = ""
    weight: float = 0.0

    def score(self, data: Dict[str, Any]) -> tuple[int, Dict[str, float]]:
        """返回 (总分, 子指标详情)"""
        raise NotImplementedError

    def _normalize(self, value: float, min_val: float, max_val: float) -> int:
        """将值归一化到 0-100"""
        if max_val == min_val:
            return 50
        normalized = (value - min_val) / (max_val - min_val)
        return max(0, min(100, int(normalized * 100)))
```

```python
# app/services/scoring/scorers/industry.py
from typing import Dict, Any, Tuple
from .base import Scorer

# 行业增长性参考值（可后续优化）
INDUSTRY_GROWTH_MAP = {
    "Technology": 80,
    "Communication Services": 75,
    "Consumer Discretionary": 70,
    "Health Care": 75,
    "Financials": 65,
    "Industrials": 60,
    "Consumer Staples": 55,
    "Materials": 50,
    "Energy": 45,
    "Utilities": 50,
    "Real Estate": 55,
}

class IndustryScorer(Scorer):
    name = "行业层"
    weight = 0.20

    def score(self, data: Dict[str, Any]) -> Tuple[int, Dict[str, float]]:
        sector = data.get("sector", "")
        industry = data.get("industry", "")
        market_cap = data.get("market_cap") or 0

        # 行业基准分
        base_score = INDUSTRY_GROWTH_MAP.get(sector, 50)

        # 市值加成（大公司更稳定）
        size_bonus = 0
        if market_cap > 500_000_000_000:  # > 5000 亿
            size_bonus = 10
        elif market_cap > 100_000_000_000:  # > 1000 亿
            size_bonus = 5

        total = min(100, base_score + size_bonus)

        return total, {
            "sector_score": base_score,
            "size_bonus": size_bonus,
            "sector": sector,
        }
```

- [ ] **Step 2: 公司层评分**

```python
# app/services/scoring/scorers/company.py
from typing import Dict, Any, Tuple
from .base import Scorer

class CompanyScorer(Scorer):
    name = "公司层"
    weight = 0.20

    def score(self, data: Dict[str, Any]) -> Tuple[int, Dict[str, float]]:
        # MVP: 简化评分逻辑，后续可扩展
        long_name = data.get("long_name", "")
        employee_count = data.get("employee_count") or 0

        # 规模评分
        size_score = 50
        if employee_count > 10000:
            size_score = 80
        elif employee_count > 1000:
            size_score = 65
        elif employee_count > 100:
            size_score = 55

        # 有网站加分
        website = data.get("website")
        if website:
            size_score = min(100, size_score + 5)

        return size_score, {
            "size_score": size_score,
            "employee_count": employee_count,
        }
```

- [ ] **Step 3: 财务层评分**

```python
# app/services/scoring/scorers/financial.py
from typing import Dict, Any, Tuple
from .base import Scorer

class FinancialScorer(Scorer):
    name = "财务层"
    weight = 0.20

    def score(self, data: Dict[str, Any]) -> Tuple[int, Dict[str, float]]:
        revenue_growth = data.get("revenue_growth") or 0  # 小数，如 0.15 = 15%
        gross_margin = data.get("gross_margin") or 0  # 小数，如 0.8 = 80%
        operating_margin = data.get("operating_margin") or 0  # 小数
        fcf_margin = data.get("fcf_margin") or 0  # 小数

        # 增长评分（0-30分）
        growth_score = 0
        if revenue_growth > 0.5:
            growth_score = 30
        elif revenue_growth > 0.3:
            growth_score = 25
        elif revenue_growth > 0.2:
            growth_score = 20
        elif revenue_growth > 0.1:
            growth_score = 15
        elif revenue_growth > 0:
            growth_score = 10
        else:
            growth_score = 0

        # 利润率评分（0-30分）
        margin_score = 0
        if gross_margin and gross_margin > 0.6:
            margin_score += 15
        elif gross_margin and gross_margin > 0.4:
            margin_score += 10

        if operating_margin and operating_margin > 0.25:
            margin_score += 15
        elif operating_margin and operating_margin > 0.1:
            margin_score += 10

        margin_score = min(30, margin_score)

        # 现金流评分（0-20分）
        fcf_score = 0
        if fcf_margin and fcf_margin > 0.2:
            fcf_score = 20
        elif fcf_margin and fcf_margin > 0.1:
            fcf_score = 15
        elif fcf_margin and fcf_margin > 0:
            fcf_score = 10

        # PE 合理性（0-20分）- 简化处理
        pe = data.get("pe_ratio")
        pe_score = 10  # 默认
        if pe:
            if 15 <= pe <= 30:
                pe_score = 20
            elif 0 < pe < 15:
                pe_score = 15
            elif pe > 50:
                pe_score = 5

        total = min(100, growth_score + margin_score + fcf_score + pe_score)

        return total, {
            "growth_score": growth_score,
            "margin_score": margin_score,
            "fcf_score": fcf_score,
            "pe_score": pe_score,
            "revenue_growth": revenue_growth,
            "gross_margin": gross_margin,
        }
```

- [ ] **Step 4: 竞争格局层评分**

```python
# app/services/scoring/scorers/competition.py
from typing import Dict, Any, Tuple
from .base import Scorer

class CompetitionScorer(Scorer):
    name = "竞争格局层"
    weight = 0.15

    def score(self, data: Dict[str, Any]) -> Tuple[int, Dict[str, float]]:
        market_cap = data.get("market_cap") or 0
        revenue_growth = data.get("revenue_growth") or 0

        # 市值规模（相对评分，MVP 简化）
        size_score = 50
        if market_cap > 1_000_000_000_000:  # > 1 万亿
            size_score = 90
        elif market_cap > 500_000_000_000:  # > 5000 亿
            size_score = 80
        elif market_cap > 100_000_000_000:  # > 1000 亿
            size_score = 70
        elif market_cap > 10_000_000_000:  # > 100 亿
            size_score = 60

        # 增速优势
        growth_score = 0
        if revenue_growth > 0.3:
            growth_score = 15
        elif revenue_growth > 0.15:
            growth_score = 10
        elif revenue_growth > 0:
            growth_score = 5

        total = min(100, size_score + growth_score)

        return total, {
            "size_score": size_score,
            "growth_score": growth_score,
            "market_cap": market_cap,
        }
```

- [ ] **Step 5: 交易结构层评分**

```python
# app/services/scoring/scorers/trading.py
from typing import Dict, Any, Tuple
from .base import Scorer

class TradingScorer(Scorer):
    name = "交易结构层"
    weight = 0.15

    def score(self, data: Dict[str, Any]) -> Tuple[int, Dict[str, float]]:
        current_price = data.get("current_price") or 0
        high_52w = data.get("fifty_two_week_high") or 0
        low_52w = data.get("fifty_two_week_low") or 0
        pe = data.get("pe_ratio")
        beta = data.get("beta") or 1.0

        # 估值位置（0-50分）
        valuation_score = 50
        if high_52w > 0 and low_52w > 0:
            price_position = (current_price - low_52w) / (high_52w - low_52w) * 100
            if price_position < 30:  # 低位
                valuation_score = 70
            elif price_position > 80:  # 高位
                valuation_score = 30

        # PE 评分（0-30分）
        pe_score = 15
        if pe:
            if 15 <= pe <= 25:
                pe_score = 30
            elif 0 < pe < 15:
                pe_score = 20
            elif 25 < pe <= 40:
                pe_score = 15
            elif pe > 40:
                pe_score = 5

        # 波动性（0-20分）- beta 越低越稳健
        volatility_score = 20
        if beta > 1.5:
            volatility_score = 5
        elif beta > 1.2:
            volatility_score = 10
        elif beta > 0.8:
            volatility_score = 20

        total = min(100, valuation_score + pe_score + volatility_score)

        return total, {
            "valuation_score": valuation_score,
            "pe_score": pe_score,
            "volatility_score": volatility_score,
            "price_position": (current_price - low_52w) / (high_52w - low_52w) * 100 if high_52w > low_52w else 50,
            "pe": pe,
            "beta": beta,
        }
```

- [ ] **Step 6: 预期差层评分**

```python
# app/services/scoring/scorers/expectation.py
from typing import Dict, Any, Tuple
from .base import Scorer

class ExpectationScorer(Scorer):
    name = "预期差层"
    weight = 0.10

    def score(self, data: Dict[str, Any]) -> Tuple[int, Dict[str, float]]:
        target_mean = data.get("target_mean_price") or 0
        current_price = data.get("current_price") or 0
        recommendation = data.get("recommendation_key", "")
        analyst_count = data.get("number_of_analyst_opinions") or 0

        # 预期空间评分（0-60分）
        upside_score = 30
        if target_mean > 0 and current_price > 0:
            upside = (target_mean - current_price) / current_price * 100
            if upside > 30:
                upside_score = 60
            elif upside > 20:
                upside_score = 50
            elif upside > 10:
                upside_score = 40
            elif upside < 0:
                upside_score = 10

        # 分析师共识（0-30分）
        consensus_score = 15
        if recommendation == "strongBuy" or recommendation == "buy":
            consensus_score = 30
        elif recommendation == "hold":
            consensus_score = 15
        elif recommendation == "sell":
            consensus_score = 5

        # 分析师数量加成（0-10分）
        analyst_score = 0
        if analyst_count >= 20:
            analyst_score = 10
        elif analyst_count >= 10:
            analyst_score = 7
        elif analyst_count >= 5:
            analyst_score = 5

        total = min(100, upside_score + consensus_score + analyst_score)

        return total, {
            "upside_score": upside_score,
            "consensus_score": consensus_score,
            "analyst_score": analyst_score,
            "upside_pct": (target_mean - current_price) / current_price * 100 if target_mean and current_price > 0 else 0,
            "recommendation": recommendation,
            "analyst_count": analyst_count,
        }
```

- [ ] **Step 7: 创建评分器入口**

```python
# app/services/scoring/scorers/__init__.py
from .industry import IndustryScorer
from .company import CompanyScorer
from .financial import FinancialScorer
from .competition import CompetitionScorer
from .trading import TradingScorer
from .expectation import ExpectationScorer

__all__ = [
    "IndustryScorer",
    "CompanyScorer",
    "FinancialScorer",
    "CompetitionScorer",
    "TradingScorer",
    "ExpectationScorer",
]
```

- [ ] **Step 8: 提交代码**

```bash
git add app/services/scoring/scorers/
git commit -m "feat: implement six-layer scorers"
```

---

### Task 3: 评分聚合器和缓存

**Files:**
- Create: `app/services/scoring/aggregator.py`
- Create: `app/services/scoring/cache.py`

- [ ] **Step 1: 创建评分聚合器**

```python
# app/services/scoring/aggregator.py
from typing import Dict, Any, List
from app.schemas.scoring import StockScore, LayerScore
from .scorers import (
    IndustryScorer,
    CompanyScorer,
    FinancialScorer,
    CompetitionScorer,
    TradingScorer,
    ExpectationScorer,
)
from app.services.scoring.data_sources.yfinance_source import YFinanceDataSource

class ScoringAggregator:
    """评分聚合器：协调数据源和评分器，计算综合评分"""

    def __init__(self):
        self.data_source = YFinanceDataSource()
        self.scorers = [
            IndustryScorer(),
            CompanyScorer(),
            FinancialScorer(),
            CompetitionScorer(),
            TradingScorer(),
            ExpectationScorer(),
        ]

    async def get_stock_score(self, symbol: str) -> StockScore:
        """获取股票综合评分"""
        # 批量获取所有数据（减少网络请求）
        data_tasks = [
            self.data_source.get_industry_data(symbol),
            self.data_source.get_company_data(symbol),
            self.data_source.get_financial_data(symbol),
            self.data_source.get_competition_data(symbol),
            self.data_source.get_trading_data(symbol),
            self.data_source.get_expectation_data(symbol),
        ]
        import asyncio
        results = await asyncio.gather(*data_tasks, return_exceptions=True)

        industry_data = results[0] if not isinstance(results[0], Exception) else {}
        company_data = results[1] if not isinstance(results[1], Exception) else {}
        financial_data = results[2] if not isinstance(results[2], Exception) else {}
        competition_data = results[3] if not isinstance(results[3], Exception) else {}
        trading_data = results[4] if not isinstance(results[4], Exception) else {}
        expectation_data = results[5] if not isinstance(results[5], Exception) else {}

        all_data = {
            **industry_data,
            **company_data,
            **financial_data,
            **competition_data,
            **trading_data,
            **expectation_data,
        }

        # 计算各层评分
        layer_scores: List[LayerScore] = []
        weighted_sum = 0.0

        scorer_map = {
            "行业层": (IndustryScorer(), industry_data),
            "公司层": (CompanyScorer(), company_data),
            "财务层": (FinancialScorer(), financial_data),
            "竞争格局层": (CompetitionScorer(), competition_data),
            "交易结构层": (TradingScorer(), trading_data),
            "预期差层": (ExpectationScorer(), expectation_data),
        }

        for name, (scorer, data) in scorer_map.items():
            score, details = scorer.score(data)
            layer_scores.append(LayerScore(
                name=name,
                score=score,
                weight=scorer.weight,
                details=details,
            ))
            weighted_sum += score * scorer.weight

        total_score = int(weighted_sum)

        return StockScore(
            symbol=symbol,
            name=all_data.get("long_name", symbol),
            current_price=all_data.get("current_price"),
            sector=all_data.get("sector"),
            industry=all_data.get("industry"),
            layers=layer_scores,
            total_score=total_score,
            timestamp=None,  # 由 API 层设置
        )

    async def get_compare_scores(self, symbols: List[str]) -> List[StockScore]:
        """获取多只股票的评分"""
        import asyncio
        scores = await asyncio.gather(*[self.get_stock_score(s) for s in symbols])
        return list(scores)
```

- [ ] **Step 2: 创建缓存层**

```python
# app/services/scoring/cache.py
import json
from typing import Optional, List
from app.cache.client import get_redis
from app.schemas.scoring import StockScore, StockListItem
from app.core.logging import logger

# 缓存 TTL 配置（秒）
SCORE_CACHE_TTL = 300  # 5 分钟
LIST_CACHE_TTL = 600   # 10 分钟

def _score_key(symbol: str) -> str:
    return f"scoring:stock:{symbol}"

def _list_key(industry: str) -> str:
    return f"scoring:list:{industry or 'all'}"

class ScoringCache:
    """评分结果缓存"""

    async def get_stock_score(self, symbol: str) -> Optional[StockScore]:
        """获取缓存的股票评分"""
        redis = await get_redis()
        try:
            data = await redis.get(_score_key(symbol))
            if data:
                logger.info("scoring_cache_hit", symbol=symbol)
                parsed = json.loads(data)
                # 反序列化时处理 datetime
                if parsed.get("timestamp"):
                    from datetime import date
                    parsed["timestamp"] = date.fromisoformat(parsed["timestamp"])
                return StockScore(**parsed)
        except Exception as e:
            logger.warning("scoring_cache_read_failed", symbol=symbol, error=str(e))
        return None

    async def set_stock_score(self, symbol: str, score: StockScore) -> None:
        """缓存股票评分"""
        redis = await get_redis()
        try:
            import json
            from datetime import date
            # 序列化时处理 datetime
            data = score.model_dump()
            if data.get("timestamp"):
                data["timestamp"] = data["timestamp"].iso() if isinstance(data["timestamp"], date) else str(data["timestamp"])
            await redis.setex(_score_key(symbol), SCORE_CACHE_TTL, json.dumps(data))
            logger.info("scoring_cache_set", symbol=symbol, ttl=SCORE_CACHE_TTL)
        except Exception as e:
            logger.warning("scoring_cache_write_failed", symbol=symbol, error=str(e))

    async def invalidate_stock(self, symbol: str) -> None:
        """使股票缓存失效"""
        redis = await get_redis()
        await redis.delete(_score_key(symbol))
```

- [ ] **Step 3: 提交代码**

```bash
git add app/services/scoring/aggregator.py app/services/scoring/cache.py
git commit -m "feat: add scoring aggregator and cache layer"
```

---

### Task 4: API 路由实现

**Files:**
- Create: `app/api/v1/scoring.py`

- [ ] **Step 1: 创建评分 API 路由**

```python
# app/api/v1/scoring.py
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from app.schemas.scoring import (
    StockScore,
    CompareRequest,
    CompareResponse,
    StockListItem,
    StockListResponse,
)
from app.services.scoring.aggregator import ScoringAggregator
from app.services.scoring.cache import ScoringCache
from app.core.logging import logger

router = APIRouter(prefix="/scoring", tags=["scoring"])
aggregator = ScoringAggregator()
cache = ScoringCache()

@router.get("/stock/{symbol}", response_model=StockScore)
async def get_stock_score(symbol: str):
    """获取单只股票的六层评分"""
    try:
        # 先检查缓存
        cached = await cache.get_stock_score(symbol)
        if cached:
            return cached

        # 计算评分
        score = await aggregator.get_stock_score(symbol)
        from datetime import date
        score.timestamp = date.today()

        # 缓存结果
        await cache.set_stock_score(symbol, score)

        return score
    except Exception as e:
        logger.exception("scoring_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=f"获取评分失败: {str(e)}")


@router.post("/compare", response_model=CompareResponse)
async def compare_stocks(request: CompareRequest):
    """对比多只股票的评分"""
    if len(request.symbols) > 5:
        raise HTTPException(status_code=400, detail="最多支持 5 只股票对比")

    try:
        scores = await aggregator.get_compare_scores(request.symbols)
        from datetime import date
        for s in scores:
            if not s.timestamp:
                s.timestamp = date.today()
        return CompareResponse(stocks=scores)
    except Exception as e:
        logger.exception("scoring_compare_failed", symbols=request.symbols, error=str(e))
        raise HTTPException(status_code=500, detail=f"对比失败: {str(e)}")


@router.get("/list", response_model=StockListResponse)
async def get_stock_list(
    sector: Optional[str] = Query(None, description="行业筛选"),
    min_score: int = Query(0, ge=0, le=100, description="最低评分"),
    max_results: int = Query(20, ge=1, le=100, description="返回数量"),
):
    """获取股票列表（带筛选）"""
    # MVP: 返回预定义股票列表，可后续接入选股逻辑
    # 这里可以从数据库或缓存获取符合条件的数据
    # 暂时返回一个空列表示例，后续扩展
    return StockListResponse(items=[], total=0)


@router.get("/report/{symbol}")
async def get_stock_report(symbol: str):
    """获取股票完整研报（后续实现）"""
    # MVP 阶段暂不实现，返回评分数据
    score = await get_stock_score(symbol)
    return {
        "symbol": symbol,
        "score": score.model_dump(),
        "report_url": None,  # 后续生成 PDF/HTML
    }
```

- [ ] **Step 2: 注册路由到 API 主入口**

```python
# app/api/v1/api.py (修改)
from fastapi import APIRouter
from . import auth, etf, fear_greed, scoring  # 添加 scoring

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(etf.router)
api_router.include_router(fear_greed.router)
api_router.include_router(scoring.router)  # 添加
```

- [ ] **Step 3: 提交代码**

```bash
git add app/api/v1/scoring.py app/api/v1/api.py
git commit -m "feat: add scoring API routes"
```

---

### Task 5: 前端 - 创建投资评分页面

**Files:**
- Create: `frontend/lib/api/scoring.ts`
- Create: `frontend/lib/store/scoring.ts`
- Create: `frontend/app/(dashboard)/scoring/page.tsx`
- Modify: `frontend/components/layout/TopNav.tsx`

- [ ] **Step 1: 创建 API 调用封装**

```typescript
// frontend/lib/api/scoring.ts
import apiClient from './client'

export interface LayerScore {
  name: string
  score: number
  weight: number
  details: Record<string, number>
}

export interface StockScore {
  symbol: string
  name: string
  current_price?: number
  sector?: string
  industry?: string
  layers: LayerScore[]
  total_score: number
  timestamp?: string
}

export interface CompareRequest {
  symbols: string[]
}

export interface CompareResponse {
  stocks: StockScore[]
}

export interface StockListItem {
  symbol: string
  name: string
  sector?: string
  total_score: number
  price?: number
  change_pct?: number
}

export const fetchStockScore = async (symbol: string): Promise<StockScore> => {
  const response = await apiClient.get<StockScore>(`/api/v1/scoring/stock/${symbol}`)
  return response.data
}

export const compareStocks = async (symbols: string[]): Promise<CompareResponse> => {
  const response = await apiClient.post<CompareResponse>('/api/v1/scoring/compare', {
    symbols,
  })
  return response.data
}
```

- [ ] **Step 2: 创建 Zustand store**

```typescript
// frontend/lib/store/scoring.ts
import { create } from 'zustand'
import type { StockScore } from '@/lib/api/scoring'

interface ScoringState {
  currentStock: string | null
  currentScore: StockScore | null
  compareStocks: string[]
  compareScores: Map<string, StockScore>
  loading: boolean
  error: string | null
  setCurrentStock: (symbol: string | null) => void
  setCurrentScore: (score: StockScore | null) => void
  addCompareStock: (symbol: string) => void
  removeCompareStock: (symbol: string) => void
  setCompareScores: (scores: StockScore[]) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  clearAll: () => void
}

export const useScoringStore = create<ScoringState>((set) => ({
  currentStock: null,
  currentScore: null,
  compareStocks: [],
  compareScores: new Map(),
  loading: false,
  error: null,
  setCurrentStock: (symbol) => set({ currentStock: symbol }),
  setCurrentScore: (score) => set({ currentScore: score }),
  addCompareStock: (symbol) =>
    set((state) => ({
      compareStocks: state.compareStocks.includes(symbol)
        ? state.compareStocks
        : [...state.compareStocks, symbol],
    })),
  removeCompareStock: (symbol) =>
    set((state) => ({
      compareStocks: state.compareStocks.filter((s) => s !== symbol),
      compareScores: new Map(
        [...state.compareScores.entries()].filter(([k]) => k !== symbol)
      ),
    })),
  setCompareScores: (scores) =>
    set((state) => {
      const newMap = new Map(state.compareScores)
      scores.forEach((s) => newMap.set(s.symbol, s))
      return { compareScores: newMap }
    }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  clearAll: () =>
    set({
      currentStock: null,
      currentScore: null,
      compareStocks: [],
      compareScores: new Map(),
      loading: false,
      error: null,
    }),
}))
```

- [ ] **Step 3: 创建评分主页面**

```typescript
// frontend/app/(dashboard)/scoring/page.tsx
'use client'

import { useState } from 'react'
import { useScoringStore } from '@/lib/store/scoring'
import { fetchStockScore, compareStocks } from '@/lib/api/scoring'
import StockSearch from './components/StockSearch'
import ScoreCard from './components/ScoreCard'
import RadarChart from './components/RadarChart'
import Spinner from '@/components/ui/Spinner'

type Tab = 'card' | 'compare' | 'list'

export default function ScoringPage() {
  const [activeTab, setActiveTab] = useState<Tab>('card')
  const {
    currentStock,
    currentScore,
    compareStocks,
    compareScores,
    loading,
    error,
    setCurrentStock,
    setCurrentScore,
    setLoading,
    setError,
  } = useScoringStore()

  const handleSearch = async (symbol: string) => {
    setLoading(true)
    setError(null)
    setCurrentStock(symbol)

    try {
      const score = await fetchStockScore(symbol)
      setCurrentScore(score)
    } catch (e) {
      setError('获取评分失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  const handleCompare = async () => {
    if (compareStocks.length < 2) {
      setError('请至少选择 2 只股票进行对比')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const result = await compareStocks(compareStocks)
      // 更新 store 中的 compareScores
      const store = useScoringStore.getState()
      store.setCompareScores(result.stocks)
    } catch (e) {
      setError('对比失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      {/* 页头 */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-gray-900">投资评分</h1>
      </div>

      {/* 子 Tab */}
      <div className="flex gap-2 mb-4 border-b border-gray-200">
        {[
          { key: 'card', label: '评分卡片' },
          { key: 'compare', label: '雷达对比' },
          { key: 'list', label: '选股列表' },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as Tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === tab.key
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 搜索框 */}
      <div className="mb-4">
        <StockSearch onSearch={handleSearch} />
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
          {error}
        </div>
      )}

      {/* 内容区域 */}
      <div className="min-h-64">
        {loading && <Spinner size={40} />}

        {!loading && activeTab === 'card' && currentScore && (
          <ScoreCard score={currentScore} />
        )}

        {!loading && activeTab === 'compare' && (
          <RadarChart scores={Array.from(compareScores.values())} />
        )}

        {!loading && activeTab === 'list' && (
          <div className="text-gray-500">选股列表功能开发中...</div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: 创建股票搜索组件**

```typescript
// frontend/app/(dashboard)/scoring/components/StockSearch.tsx
import { useState } from 'react'

interface StockSearchProps {
  onSearch: (symbol: string) => void
}

export default function StockSearch({ onSearch }: StockSearchProps) {
  const [symbol, setSymbol] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (symbol.trim()) {
      onSearch(symbol.trim().toUpperCase())
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={symbol}
        onChange={(e) => setSymbol(e.target.value)}
        placeholder="输入股票代码，如 AAPL"
        className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <button
        type="submit"
        className="px-6 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
      >
        查询
      </button>
    </form>
  )
}
```

- [ ] **Step 5: 创建评分卡片组件**

```typescript
// frontend/app/(dashboard)/scoring/components/ScoreCard.tsx
import type { StockScore } from '@/lib/api/scoring'

interface ScoreCardProps {
  score: StockScore
}

const LAYER_COLORS = [
  'bg-blue-500',
  'bg-green-500',
  'bg-yellow-500',
  'bg-purple-500',
  'bg-pink-500',
  'bg-indigo-500',
]

export default function ScoreCard({ score }: ScoreCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      {/* 股票信息 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-900">{score.name}</h2>
          <p className="text-sm text-gray-500">
            {score.symbol} {score.sector && `· ${score.sector}`}
          </p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-bold text-blue-600">{score.total_score}</div>
          <div className="text-sm text-gray-500">综合评分</div>
        </div>
      </div>

      {/* 六层评分 */}
      <div className="space-y-4">
        {score.layers.map((layer, index) => (
          <div key={layer.name} className="flex items-center gap-4">
            <div className="w-20 text-sm font-medium text-gray-700">{layer.name}</div>
            <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full ${LAYER_COLORS[index]} transition-all`}
                style={{ width: `${layer.score}%` }}
              />
            </div>
            <div className="w-10 text-sm font-medium text-gray-900 text-right">
              {layer.score}
            </div>
          </div>
        ))}
      </div>

      {/* 当前价格 */}
      {score.current_price && (
        <div className="mt-6 pt-4 border-t border-gray-100 text-center">
          <span className="text-gray-500">当前价格: </span>
          <span className="text-lg font-bold text-gray-900">${score.current_price.toFixed(2)}</span>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 6: 创建雷达图组件**

```typescript
// frontend/app/(dashboard)/scoring/components/RadarChart.tsx
'use client'

import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { StockScore } from '@/lib/api/scoring'

interface RadarChartProps {
  scores: StockScore[]
}

export default function RadarChart({ scores }: RadarChartProps) {
  const chartRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!chartRef.current || scores.length === 0) return

    const chart = echarts.init(chartRef.current)

    const indicator = scores[0].layers.map((layer) => ({
      name: layer.name,
      max: 100,
    }))

    const series = scores.map((stock, index) => ({
      value: stock.layers.map((layer) => layer.score),
      name: stock.symbol,
      lineStyle: { width: 2 },
    }))

    const option = {
      legend: {
        data: scores.map((s) => s.symbol),
      },
      radar: {
        indicator,
        shape: 'polygon',
      },
      series: [
        {
          type: 'radar',
          data: series,
        },
      ],
    }

    chart.setOption(option)

    return () => chart.dispose()
  }, [scores])

  if (scores.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        请先添加股票进行对比
      </div>
    )
  }

  return <div ref={chartRef} className="w-full h-96" />
}
```

- [ ] **Step 7: 修改导航栏添加投资评分入口**

```typescript
// frontend/components/layout/TopNav.tsx (修改)
const NAV_ITEMS = [
  { href: '/dashboard', label: '仪表盘' },
  { href: '/fear-greed', label: '恐慌指数' },
  { href: '/etf', label: 'ETF 资金流' },
  { href: '/scoring', label: '投资评分' },  // 添加这一行
  { href: '/chat', label: 'AI 对话' },
  { href: '/settings', label: '设置' },
] as const
```

- [ ] **Step 8: 提交代码**

```bash
git add frontend/lib/api/scoring.ts frontend/lib/store/scoring.ts
git add frontend/app/\(dashboard\)/scoring/
git add frontend/components/layout/TopNav.tsx
git commit -m "feat: add scoring frontend page and components"
```

---

### Task 6: 集成测试

**Files:**
- Create: `tests/services/scoring/test_scorers.py`
- Create: `tests/api/v1/test_scoring.py`

- [ ] **Step 1: 创建评分器单元测试**

```python
# tests/services/scoring/test_scorers.py
import pytest
from app.services.scoring.scorers.industry import IndustryScorer
from app.services.scoring.scorers.financial import FinancialScorer
from app.services.scoring.scorers.trading import TradingScorer

class TestIndustryScorer:
    def test_tech_sector_high_score(self):
        scorer = IndustryScorer()
        data = {"sector": "Technology", "market_cap": 1_000_000_000_000}
        score, details = scorer.score(data)
        assert score >= 70
        assert details["sector"] == "Technology"

    def test_unknown_sector_default_score(self):
        scorer = IndustryScorer()
        data = {"sector": "Unknown"}
        score, details = scorer.score(data)
        assert score == 50

class TestFinancialScorer:
    def test_high_growth_high_margin(self):
        scorer = FinancialScorer()
        data = {
            "revenue_growth": 0.25,
            "gross_margin": 0.7,
            "operating_margin": 0.3,
            "fcf_margin": 0.25,
            "pe_ratio": 25,
        }
        score, details = scorer.score(data)
        assert score >= 60

    def test_negative_growth_low_score(self):
        scorer = FinancialScorer()
        data = {
            "revenue_growth": -0.1,
            "gross_margin": 0.3,
            "pe_ratio": 50,
        }
        score, details = scorer.score(data)
        assert score < 50

class TestTradingScorer:
    def test_low_price_position_better(self):
        scorer = TradingScorer()
        data = {
            "current_price": 100,
            "fifty_two_week_high": 200,
            "fifty_two_week_low": 50,
            "pe_ratio": 20,
            "beta": 1.0,
        }
        score, details = scorer.score(data)
        assert score >= 50
```

- [ ] **Step 2: 创建 API 集成测试**

```python
# tests/api/v1/test_scoring.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestScoringAPI:
    def test_get_stock_score(self):
        response = client.get("/api/v1/scoring/stock/AAPL")
        assert response.status_code == 200
        data = response.json()
        assert "symbol" in data
        assert "layers" in data
        assert len(data["layers"]) == 6

    def test_compare_stocks(self):
        response = client.post(
            "/api/v1/scoring/compare",
            json={"symbols": ["AAPL", "MSFT"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["stocks"]) == 2

    def test_invalid_symbol(self):
        response = client.get("/api/v1/scoring/stock/INVALID_SYMBOL_12345")
        # 应该返回 500 或 200（即使无数据）
        assert response.status_code in [200, 500]
```

- [ ] **Step 3: 运行测试并提交**

```bash
cd /Users/hanqing.zf/PycharmProjects/deepalpha-club-ai
uv run pytest tests/services/scoring/ tests/api/v1/test_scoring.py -v
git add tests/
git commit -m "test: add scoring tests"
```

---

## 验收标准检查清单

- [ ] 后端 API `/api/v1/scoring/stock/{symbol}` 返回六层评分
- [ ] 后端 API `/api/v1/scoring/compare` 支持多股票对比
- [ ] 前端"投资评分" Tab 页面正常显示
- [ ] 前端股票搜索功能正常
- [ ] 前端评分卡片正确展示六层得分
- [ ] 前端雷达图正确展示对比数据
- [ ] 所有 Redis 缓存正常工作
- [ ] yfinance 数据获取正常
- [ ] 视觉风格与现有页面一致

---

## 后续迭代

1. **研报视图** — 生成完整研报 PDF/HTML
2. **选股列表** — 接入数据库，支持行业/评分筛选
3. **NewsAPI 集成** — 预期差层接入新闻情绪
4. **评分算法优化** — 根据用户反馈调整各层权重
5. **数据源扩展** — 接入 FMP API 获取更完整财务数据