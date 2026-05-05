# ETF 资金流热力图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `/etf` 页面展示 75 只美股 ETF 的 CLV 资金流强度热力图，按板块分组，支持日/周/月粒度切换。

**Architecture:** 后端单一 `GET /api/v1/etf/heatmap` 端点：从 FMP 获取全部 75 只 ETF 的 OHLCV → 计算 CLV×价格×成交量得到 Flow → 跨全样本 Z-score 标准化得到 Intensity → 按粒度聚合 → Redis 缓存（TTL 3600s）。前端 Zustand 管理粒度状态，ETFHeatmapTable 渲染折叠分组 + 红绿热力色。

**Tech Stack:** Python httpx + FMP API, FastAPI, asyncio Redis, Next.js 16 App Router, TypeScript, Tailwind CSS v4, Zustand 5

---

## 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `app/schemas/etf.py` | 新增 HeatmapCell / HeatmapETFRow / HeatmapSectorGroup / HeatmapResponse |
| 修改 | `app/services/etf/fetcher.py` | 替换为 75 只 ETF + 中文名，更新 OHLCV 字段，添加 CLV/Flow/Intensity 计算和 build_heatmap_data |
| 修改 | `app/cache/etf_cache.py` | 新增 get_heatmap_cache / set_heatmap_cache |
| 新增 | `app/api/v1/etf.py` | GET /etf/heatmap 端点 |
| 修改 | `app/api/v1/api.py` | 挂载 etf_router |
| 新增 | `tests/test_etf_heatmap.py` | CLV/Flow/Intensity 计算单元测试 + 端点测试 |
| 新增 | `frontend/lib/api/etf.ts` | Axios API 函数 + TypeScript 类型 |
| 新增 | `frontend/lib/store/etf.ts` | Zustand store（granularity + days）|
| 新增 | `frontend/components/etf/GranularityToggle.tsx` | 日/周/月切换按钮组 |
| 新增 | `frontend/components/etf/ETFHeatmapTable.tsx` | 热力图主表格（折叠、颜色、横向滚动）|
| 修改 | `frontend/app/(dashboard)/etf/page.tsx` | 替换骨架，组合以上组件 |

---

## Task 1: 更新后端 Schema

**Files:**
- 修改: `app/schemas/etf.py`

- [ ] **Step 1: 写 failing test**

新建 `tests/test_etf_heatmap.py`：

```python
"""ETF 热力图相关测试。"""
import pytest
from app.schemas.etf import HeatmapCell, HeatmapETFRow, HeatmapSectorGroup, HeatmapResponse


def test_heatmap_cell_valid():
    cell = HeatmapCell(date="2026-04-24", intensity=1.23)
    assert cell.date == "2026-04-24"
    assert cell.intensity == 1.23


def test_heatmap_cell_allows_none_intensity():
    cell = HeatmapCell(date="2026-04-24", intensity=None)
    assert cell.intensity is None


def test_heatmap_response_structure():
    response = HeatmapResponse(
        granularity="day",
        days=30,
        date_labels=["2026-04-24"],
        sectors=[
            HeatmapSectorGroup(
                sector="01 信息技术",
                avg_cells=[HeatmapCell(date="2026-04-24", intensity=0.5)],
                etfs=[
                    HeatmapETFRow(
                        symbol="XLK",
                        name="科技行业精选指数ETF-SPDR",
                        cells=[HeatmapCell(date="2026-04-24", intensity=1.2)],
                    )
                ],
            )
        ],
    )
    assert response.granularity == "day"
    assert len(response.sectors) == 1
    assert response.sectors[0].etfs[0].symbol == "XLK"
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
uv run pytest tests/test_etf_heatmap.py -v 2>&1 | head -30
```

预期：`ImportError: cannot import name 'HeatmapCell'`

- [ ] **Step 3: 更新 app/schemas/etf.py，追加四个新类**

```python
"""ETF 资金流看板 Pydantic schemas。"""

import datetime
from typing import List, Optional

from pydantic import Field

from app.schemas.base import BaseResponse


class FlowDataPoint(BaseResponse):
    """单只 ETF 某一交易日的资金流数据点。"""

    symbol: str = Field(description="ETF 代码，如 SPY")
    date: datetime.date = Field(description="交易日期")
    close: float = Field(description="收盘价（USD）")
    volume: int = Field(ge=0, description="成交量（股数）")
    dollar_volume: float = Field(description="美元成交量 = volume × close（资金流代理指标）")
    return_pct: float = Field(description="日涨跌幅（%）")


class ETFSummary(BaseResponse):
    """ETF 列表接口中每只 ETF 的汇总数据。"""

    symbol: str
    name: str
    category: str
    current_price: float
    price_change_pct: float = Field(description="所选周期总涨跌幅（%）")
    period_dollar_volume: float = Field(description="所选周期累计美元成交量（USD）")


class ETFFlowsResponse(BaseResponse):
    """GET /etf/flows/{symbol} 响应体。"""

    symbol: str
    name: str
    period: str
    flows: List[FlowDataPoint]


class ETFListResponse(BaseResponse):
    """GET /etf/list 响应体。"""

    period: str
    etfs: List[ETFSummary]


# ── 热力图相关 Schema ──────────────────────────────────────────────────────────

class HeatmapCell(BaseResponse):
    """热力图单元格：某只 ETF 在某日期的标准化强度。"""

    date: str = Field(description="日期标签，格式因粒度而异：day='2026-04-24'，week='2026-W18'，month='2026-04'")
    intensity: Optional[float] = Field(None, description="Z-score 标准化后的资金流强度，None 表示无数据")


class HeatmapETFRow(BaseResponse):
    """热力图中单只 ETF 的一行数据。"""

    symbol: str
    name: str
    cells: List[HeatmapCell]


class HeatmapSectorGroup(BaseResponse):
    """热力图中一个板块的分组数据（含板块均值行和 ETF 明细）。"""

    sector: str = Field(description="板块名称，如 '01 信息技术'")
    avg_cells: List[HeatmapCell] = Field(description="板块内所有 ETF 的强度均值，用于折叠状态展示")
    etfs: List[HeatmapETFRow]


class HeatmapResponse(BaseResponse):
    """GET /etf/heatmap 响应体。"""

    granularity: str = Field(description="粒度：day | week | month")
    days: int = Field(description="请求的交易日数量")
    date_labels: List[str] = Field(description="所有列的日期标签（升序，最新在末尾）")
    sectors: List[HeatmapSectorGroup]
```

- [ ] **Step 4: 运行确认通过**

```bash
uv run pytest tests/test_etf_heatmap.py -v
```

预期：3 个 PASS

- [ ] **Step 5: 提交**

```bash
git add app/schemas/etf.py tests/test_etf_heatmap.py
git commit -m "feat: 新增热力图 Schema（HeatmapCell/ETFRow/SectorGroup/Response）"
```

---

## Task 2: 更新 ETF 数据集 + 计算逻辑

**Files:**
- 修改: `app/services/etf/fetcher.py`

- [ ] **Step 1: 写 failing test（追加到 tests/test_etf_heatmap.py）**

```python
from unittest.mock import patch, MagicMock
from app.services.etf.fetcher import compute_clv, compute_flow, z_score_normalize, ETF_LIBRARY, CHINESE_NAMES


def test_compute_clv_mid_range():
    # close 在 high/low 正中间 → CLV = 0
    assert compute_clv(adj_close=10.0, high=12.0, low=8.0) == pytest.approx(0.0)


def test_compute_clv_at_high():
    # close = high → CLV = 1
    assert compute_clv(adj_close=12.0, high=12.0, low=8.0) == pytest.approx(1.0)


def test_compute_clv_at_low():
    # close = low → CLV = -1
    assert compute_clv(adj_close=8.0, high=12.0, low=8.0) == pytest.approx(-1.0)


def test_compute_clv_high_equals_low():
    # H=L 时不应除零
    result = compute_clv(adj_close=10.0, high=10.0, low=10.0)
    assert isinstance(result, float)


def test_compute_flow():
    clv = 0.5
    adj_close = 100.0
    volume = 1_000_000
    assert compute_flow(clv, adj_close, volume) == pytest.approx(50_000_000.0)


def test_z_score_normalize_known_values():
    flows = [1.0, 2.0, 3.0]
    result = z_score_normalize(flows)
    # mean=2, std=1 → [-1, 0, 1]
    assert result[0] == pytest.approx(-1.0)
    assert result[1] == pytest.approx(0.0)
    assert result[2] == pytest.approx(1.0)


def test_z_score_normalize_constant_returns_zeros():
    flows = [5.0, 5.0, 5.0]
    result = z_score_normalize(flows)
    assert all(r == pytest.approx(0.0) for r in result)


def test_etf_library_has_12_sectors():
    assert len(ETF_LIBRARY) == 12


def test_chinese_names_covers_all_etfs():
    all_symbols = [sym for symbols in ETF_LIBRARY.values() for sym in symbols]
    for sym in all_symbols:
        assert sym in CHINESE_NAMES, f"{sym} 缺少中文名"
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_etf_heatmap.py::test_compute_clv_mid_range -v
```

预期：`ImportError: cannot import name 'compute_clv'`

- [ ] **Step 3: 完整替换 app/services/etf/fetcher.py**

```python
"""ETF OHLCV 数据抓取与资金流计算（Financial Modeling Prep API）。

资金流计算：
  CLV = (2×adjClose - high - low) / (high - low + 1e-9)
  Flow = CLV × adjClose × volume
  Intensity = Z-score(Flow)  跨全部 ETF × 全部交易日标准化
"""

import datetime
import math
from typing import Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.etf import (
    ETFSummary,
    FlowDataPoint,
    HeatmapCell,
    HeatmapETFRow,
    HeatmapResponse,
    HeatmapSectorGroup,
)

# ── ETF 数据集 ─────────────────────────────────────────────────────────────────

CHINESE_NAMES: Dict[str, str] = {
    "XLK": "科技行业精选指数ETF-SPDR",
    "SOXX": "iShares半导体指数ETF",
    "AIQ": "Global X人工智能与科技ETF",
    "SKYY": "First Trust云计算指数ETF",
    "QTUM": "Defiance量子计算与机器学习ETF",
    "BUG": "Global X网络安全指数ETF",
    "IGV": "iShares扩张科技软件行业ETF",
    "XLV": "医疗保健行业精选指数ETF-SPDR",
    "XHE": "SPDR标普健康医疗设备ETF",
    "IHF": "iShares美国医疗保健提供商ETF",
    "XBI": "SPDR标普生物技术ETF",
    "PJP": "Invesco动力制药ETF",
    "XLF": "金融行业精选指数ETF-SPDR",
    "KBE": "SPDR标普银行指数ETF",
    "IYG": "iShares美国金融服务ETF",
    "KIE": "SPDR标普保险ETF",
    "BLOK": "Amplify转型数据共享ETF(区块链)",
    "KCE": "SPDR标普资本Market ETF",
    "REM": "iShares抵押贷款地产投资信托ETF",
    "XLY": "可选消费行业精选指数ETF-SPDR",
    "CARZ": "First Trust纳斯达克全球汽车指数ETF",
    "XRT": "SPDR标普零售业ETF",
    "XHB": "SPDR标普家居建设ETF",
    "PEJ": "Invesco休闲娱乐ETF",
    "XLP": "必需消费行业精选指数ETF-SPDR",
    "PBJ": "Invesco动力食品饮料ETF",
    "MOO": "VanEck全球农产品ETF",
    "XLI": "工业行业精选指数ETF-SPDR",
    "ITA": "iShares美国航空航天与国防ETF",
    "PKB": "Invesco动力住宅建设ETF",
    "PAVE": "Global X美国基础设施发展ETF",
    "IYT": "iShares交通运输ETF",
    "JETS": "U.S. Global Jets航空业ETF",
    "BOAT": "SonicShares全球航运ETF",
    "IFRA": "iShares美国基础设施ETF",
    "UFO": "Procure太空ETF",
    "SHLD": "Strive美国国防与航空航天ETF",
    "XLE": "能源行业精选指数ETF-SPDR",
    "IEZ": "iShares美国石油设备与服务ETF",
    "XOP": "SPDR标普石油天然气开采ETF",
    "FAN": "First Trust全球风能ETF",
    "TAN": "Invesco太阳能ETF",
    "NLR": "VanEck铀及核能ETF",
    "XLB": "原材料行业精选指数ETF-SPDR",
    "XME": "SPDR标普金属与采矿ETF",
    "WOOD": "iShares全球林业ETF",
    "COPX": "Global X铜矿股ETF",
    "GLD": "SPDR黄金ETF",
    "GLTR": "Aberdeen标准实物贵金属篮子ETF",
    "SLV": "iShares白银ETF",
    "SLX": "VanEck矢量钢铁ETF",
    "BATT": "Amplify锂电池及关键材料ETF",
    "XLC": "通信服务行业精选指数ETF-SPDR",
    "IYZ": "iShares美国电信ETF",
    "PNQI": "Invesco纳斯达克互联网ETF",
    "XLRE": "房地产行业精选指数ETF-SPDR",
    "INDS": "Pacer工业地产ETF",
    "REZ": "iShares住宅与多户家庭地产投资信托ETF",
    "SRVR": "Pacer数据基础设施与房地产ETF",
    "XLU": "公用事业行业精选指数ETF-SPDR",
    "ICLN": "iShares全球清洁能源ETF",
    "PHO": "Invesco水资源ETF",
    "GRID": "First Trust纳斯达克智能电网基础设施ETF",
    "QQQ": "Invesco纳斯达克100指数ETF",
    "SPY": "SPDR标普500指数ETF",
    "TLT": "iShares 20年期以上美国国债ETF",
    "EEM": "iShares MSCI新兴市场ETF",
    "VEA": "Vanguard FTSE发达市场ETF",
    "FXI": "iShares中国大盘股ETF",
    "ARKK": "ARK创新ETF",
    "BITO": "ProShares比特币策略ETF",
    "MSOS": "AdvisorShares纯大麻ETF",
    "IPO": "Renaissance IPO ETF",
    "GBTC": "灰度比特币现货ETF",
    "ETHE": "灰度以太坊现货ETF",
}

ETF_LIBRARY: Dict[str, List[str]] = {
    "01 信息技术": ["XLK", "SOXX", "AIQ", "SKYY", "QTUM", "BUG", "IGV"],
    "02 医疗保健": ["XLV", "XHE", "IHF", "XBI", "PJP"],
    "03 金融": ["XLF", "KBE", "IYG", "KIE", "BLOK", "KCE", "REM"],
    "04 可选消费": ["XLY", "CARZ", "XRT", "XHB", "PEJ"],
    "05 必需消费": ["XLP", "PBJ", "MOO"],
    "06 工业": ["XLI", "ITA", "PKB", "PAVE", "IYT", "JETS", "BOAT", "IFRA", "UFO", "SHLD"],
    "07 能源": ["XLE", "IEZ", "XOP", "FAN", "TAN", "NLR"],
    "08 原材料": ["XLB", "PKB", "XME", "WOOD", "COPX", "GLD", "GLTR", "SLV", "SLX", "BATT"],
    "09 通信服务": ["XLC", "IYZ", "PNQI"],
    "10 房地产": ["XLRE", "INDS", "REZ", "SRVR"],
    "11 公用事业": ["XLU", "ICLN", "PHO", "GRID"],
    "12 全球宏观/另类": ["TLT", "EEM", "VEA", "FXI", "ARKK", "BITO", "MSOS", "IPO", "UFO", "GBTC", "ETHE"],
}

# 保留原有数据以兼容旧端点
TRACKED_ETFS: List[dict] = [
    {"symbol": sym, "name": CHINESE_NAMES.get(sym, sym), "category": sector}
    for sector, symbols in ETF_LIBRARY.items()
    for sym in symbols
]

_FMP_BASE = "https://financialmodelingprep.com/api/v3"

# period → FMP timeseries 天数（ytd 单独处理）
_TIMESERIES_MAP = {
    "1w": 7,
    "1mo": 31,
    "3mo": 92,
    "1y": 365,
}


# ── 计算函数 ──────────────────────────────────────────────────────────────────

def compute_clv(adj_close: float, high: float, low: float) -> float:
    """计算 Close Location Value。

    CLV = (2×adjClose - high - low) / (high - low + 1e-9)
    范围 [-1, 1]，1e-9 避免 high=low 时除零。
    """
    return (2 * adj_close - high - low) / (high - low + 1e-9)


def compute_flow(clv: float, adj_close: float, volume: int) -> float:
    """计算资金流原始值：Flow = CLV × adjClose × volume。"""
    return clv * adj_close * volume


def z_score_normalize(flows: List[float]) -> List[float]:
    """对 flows 列表做 Z-score 标准化。

    标准差为 0（常数序列）时返回全零列表。
    """
    if not flows:
        return []
    n = len(flows)
    mean = sum(flows) / n
    variance = sum((f - mean) ** 2 for f in flows) / n
    std = math.sqrt(variance)
    if std < 1e-9 or not math.isfinite(std):
        return [0.0] * n
    return [(f - mean) / std for f in flows]


# ── FMP 数据抓取 ──────────────────────────────────────────────────────────────

def _build_url(symbol: str, period: str) -> str:
    """构造 FMP historical-price-full 请求 URL。"""
    api_key = settings.FMP_API_KEY
    if period == "ytd":
        start = datetime.date(datetime.date.today().year, 1, 1).isoformat()
        today = datetime.date.today().isoformat()
        return f"{_FMP_BASE}/historical-price-full/{symbol}?from={start}&to={today}&apikey={api_key}"
    timeseries = _TIMESERIES_MAP.get(period, 31)
    return f"{_FMP_BASE}/historical-price-full/{symbol}?timeseries={timeseries}&apikey={api_key}"


def _build_heatmap_url(symbol: str, days: int) -> str:
    """构造热力图专用 FMP URL，天数 × 2 换算为日历天数保证覆盖足够交易日。"""
    api_key = settings.FMP_API_KEY
    timeseries = days * 2
    return f"{_FMP_BASE}/historical-price-full/{symbol}?timeseries={timeseries}&apikey={api_key}"


def fetch_etf_flows(symbol: str, period: str) -> List[FlowDataPoint]:
    """抓取单只 ETF 的 OHLCV 历史数据并计算资金流指标（保留旧接口兼容）。"""
    url = _build_url(symbol, period)
    try:
        resp = httpx.get(url, timeout=15)
        resp.raise_for_status()
        historical = resp.json().get("historical", [])
    except Exception as e:
        logger.exception("fmp_fetch_failed", symbol=symbol, period=period, error=str(e))
        return []

    if not historical:
        logger.warning("fmp_empty_data", symbol=symbol, period=period)
        return []

    historical = list(reversed(historical))
    points: List[FlowDataPoint] = []
    prev_close: Optional[float] = None

    for row in historical:
        close = float(row["close"])
        volume = int(row.get("volume") or 0)
        dollar_volume = close * volume
        return_pct = 0.0 if prev_close is None else (close - prev_close) / prev_close * 100

        points.append(
            FlowDataPoint(
                symbol=symbol,
                date=datetime.date.fromisoformat(row["date"]),
                close=round(close, 4),
                volume=volume,
                dollar_volume=round(dollar_volume, 2),
                return_pct=round(return_pct, 4),
            )
        )
        prev_close = close

    return points


def fetch_etf_list_summary(period: str) -> List[ETFSummary]:
    """抓取所有跟踪 ETF 在指定周期内的汇总数据（保留旧接口兼容）。"""
    summaries: List[ETFSummary] = []
    for etf_meta in TRACKED_ETFS:
        symbol = etf_meta["symbol"]
        flows = fetch_etf_flows(symbol, period)
        if not flows:
            continue
        current_price = flows[-1].close
        first_close = flows[0].close
        price_change_pct = (current_price - first_close) / first_close * 100 if first_close else 0.0
        period_dollar_volume = sum(p.dollar_volume for p in flows)
        summaries.append(
            ETFSummary(
                symbol=symbol,
                name=etf_meta["name"],
                category=etf_meta["category"],
                current_price=round(current_price, 4),
                price_change_pct=round(price_change_pct, 4),
                period_dollar_volume=round(period_dollar_volume, 2),
            )
        )
    return summaries


# ── 热力图数据构建 ────────────────────────────────────────────────────────────

def _date_label(date_str: str, granularity: str) -> str:
    """将 'YYYY-MM-DD' 转换为对应粒度的标签。"""
    d = datetime.date.fromisoformat(date_str)
    if granularity == "week":
        iso = d.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if granularity == "month":
        return f"{d.year}-{d.month:02d}"
    return date_str  # day


def build_heatmap_data(granularity: str = "day", days: int = 30) -> HeatmapResponse:
    """构建热力图完整数据。

    步骤：
    1. 从 FMP 抓取全部 ETF 的 OHLCV
    2. 计算每日 CLV → Flow
    3. 跨全样本 Z-score 标准化得到 Intensity
    4. 按粒度聚合（day=直接使用，week/month=均值）
    5. 按 ETF_LIBRARY 分组，计算板块均值
    6. 返回 HeatmapResponse
    """
    # Step 1: 抓取所有 ETF 原始数据
    # raw_data[symbol] = [(date_str, adj_close, high, low, volume), ...]（升序）
    raw_data: Dict[str, List[Tuple[str, float, float, float, int]]] = {}

    all_symbols = [sym for symbols in ETF_LIBRARY.values() for sym in symbols]
    # 去重（PKB 和 UFO 在多个板块出现）
    seen: set = set()
    unique_symbols = [s for s in all_symbols if not (s in seen or seen.add(s))]

    for symbol in unique_symbols:
        url = _build_heatmap_url(symbol, days)
        try:
            resp = httpx.get(url, timeout=15)
            resp.raise_for_status()
            historical = resp.json().get("historical", [])
        except Exception as e:
            logger.exception("fmp_heatmap_fetch_failed", symbol=symbol, error=str(e))
            continue

        if not historical:
            continue

        # FMP 返回降序，反转为升序；只取最近 days 个交易日
        rows = list(reversed(historical))[-days:]
        raw_data[symbol] = [
            (
                row["date"],
                float(row.get("adjClose") or row.get("close") or 0),
                float(row.get("high") or 0),
                float(row.get("low") or 0),
                int(row.get("volume") or 0),
            )
            for row in rows
        ]

    # Step 2: 计算每个数据点的 CLV 和 Flow
    # symbol_flows[symbol][(date_str, label)] = flow
    symbol_flows: Dict[str, Dict[str, float]] = {}
    all_flow_values: List[float] = []
    all_flow_keys: List[Tuple[str, str]] = []  # (symbol, date_str)

    for symbol, rows in raw_data.items():
        symbol_flows[symbol] = {}
        for date_str, adj_close, high, low, volume in rows:
            clv = compute_clv(adj_close, high, low)
            flow = compute_flow(clv, adj_close, volume)
            symbol_flows[symbol][date_str] = flow
            all_flow_values.append(flow)
            all_flow_keys.append((symbol, date_str))

    # Step 3: 跨全样本 Z-score 标准化
    normalized = z_score_normalize(all_flow_values)
    # 重建为 symbol_intensity[symbol][date_str] = intensity
    symbol_intensity: Dict[str, Dict[str, float]] = {}
    for (symbol, date_str), intensity in zip(all_flow_keys, normalized):
        if symbol not in symbol_intensity:
            symbol_intensity[symbol] = {}
        symbol_intensity[symbol][date_str] = intensity

    # Step 4: 按粒度聚合
    # symbol_agg[symbol][label] = [intensity, ...]  → 取均值
    symbol_agg: Dict[str, Dict[str, List[float]]] = {}
    for symbol, date_intensity in symbol_intensity.items():
        symbol_agg[symbol] = {}
        for date_str, intensity in date_intensity.items():
            label = _date_label(date_str, granularity)
            symbol_agg[symbol].setdefault(label, []).append(intensity)

    # 得出有序 date_labels（取所有 symbol 出现过的 label 的并集，升序）
    all_labels: set = set()
    for sym_labels in symbol_agg.values():
        all_labels.update(sym_labels.keys())
    date_labels = sorted(all_labels)

    # Step 5: 按 ETF_LIBRARY 分组，构建 HeatmapSectorGroup
    sectors: List[HeatmapSectorGroup] = []

    for sector_name, sector_symbols in ETF_LIBRARY.items():
        etf_rows: List[HeatmapETFRow] = []

        for symbol in sector_symbols:
            if symbol not in symbol_agg:
                # 该 ETF 数据抓取失败，用 None 填充
                cells = [HeatmapCell(date=label, intensity=None) for label in date_labels]
            else:
                cells = [
                    HeatmapCell(
                        date=label,
                        intensity=round(
                            sum(symbol_agg[symbol].get(label, [])) / len(symbol_agg[symbol][label])
                            if symbol_agg[symbol].get(label)
                            else 0.0,
                            4,
                        ),
                    )
                    for label in date_labels
                ]
            etf_rows.append(
                HeatmapETFRow(
                    symbol=symbol,
                    name=CHINESE_NAMES.get(symbol, symbol),
                    cells=cells,
                )
            )

        # 板块均值：对每个 label，平均所有 ETF 的 intensity（跳过 None）
        avg_cells: List[HeatmapCell] = []
        for label in date_labels:
            values = [
                row.cells[i].intensity
                for row in etf_rows
                for i, cell in enumerate(row.cells)
                if cell.date == label and cell.intensity is not None
            ]
            avg_intensity = round(sum(values) / len(values), 4) if values else None
            avg_cells.append(HeatmapCell(date=label, intensity=avg_intensity))

        sectors.append(
            HeatmapSectorGroup(
                sector=sector_name,
                avg_cells=avg_cells,
                etfs=etf_rows,
            )
        )

    return HeatmapResponse(
        granularity=granularity,
        days=days,
        date_labels=date_labels,
        sectors=sectors,
    )
```

- [ ] **Step 4: 运行计算函数相关测试**

```bash
uv run pytest tests/test_etf_heatmap.py -k "clv or flow or normalize or library or chinese" -v
```

预期：全部 PASS（不含 API 端点测试，那些后续再跑）

- [ ] **Step 5: 提交**

```bash
git add app/services/etf/fetcher.py tests/test_etf_heatmap.py
git commit -m "feat: 75 只 ETF 数据集 + CLV/Flow/Intensity 计算函数"
```

---

## Task 3: 添加热力图缓存操作

**Files:**
- 修改: `app/cache/etf_cache.py`

- [ ] **Step 1: 在 app/cache/etf_cache.py 末尾追加以下内容**

```python
async def get_heatmap_cache(redis: Redis, granularity: str, days: int) -> Optional["HeatmapResponse"]:
    """读取热力图缓存，未命中返回 None。"""
    from app.schemas.etf import HeatmapResponse  # 避免循环导入
    key = f"etf:heatmap:{granularity}:{days}"
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        return HeatmapResponse(**json.loads(raw))
    except Exception as e:
        logger.warning("etf_heatmap_cache_deserialize_error", key=key, error=str(e))
        return None


async def set_heatmap_cache(redis: Redis, granularity: str, days: int, data: "HeatmapResponse") -> None:
    """将热力图数据写入 Redis，TTL = 3600s。"""
    key = f"etf:heatmap:{granularity}:{days}"
    payload = json.dumps(data.model_dump(mode="json"), ensure_ascii=False)
    await redis.set(key, payload, ex=ETF_FLOW_TTL)
    logger.info("etf_heatmap_cache_set", granularity=granularity, days=days)
```

注意：`Optional` 和 `"HeatmapResponse"` 已通过文件顶部的 `from typing import List, Optional` 可用，但 `HeatmapResponse` 用字符串前向引用避免循环导入。

- [ ] **Step 2: 提交**

```bash
git add app/cache/etf_cache.py
git commit -m "feat: 添加热力图 Redis 缓存操作（get/set_heatmap_cache）"
```

---

## Task 4: 创建 ETF API 路由并挂载

**Files:**
- 新增: `app/api/v1/etf.py`
- 修改: `app/api/v1/api.py`

- [ ] **Step 1: 创建 app/api/v1/etf.py**

```python
"""ETF 资金流热力图 API 端点。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.cache.client import get_redis
from app.cache.etf_cache import get_heatmap_cache, set_heatmap_cache
from app.core.logging import logger
from app.schemas.etf import HeatmapResponse
from app.services.etf.fetcher import build_heatmap_data

router = APIRouter()


@router.get("/heatmap", response_model=HeatmapResponse)
async def get_etf_heatmap(
    granularity: Annotated[str, Query(pattern="^(day|week|month)$")] = "day",
    days: Annotated[int, Query(ge=5, le=90)] = 30,
    redis: Redis = Depends(get_redis),
) -> HeatmapResponse:
    """获取 ETF 资金流热力图数据。

    - granularity: 粒度，day | week | month
    - days: 交易日数量，5-90，默认 30
    """
    # 尝试从缓存读取
    cached = await get_heatmap_cache(redis, granularity, days)
    if cached is not None:
        logger.info("etf_heatmap_cache_hit", granularity=granularity, days=days)
        return cached

    # 缓存未命中：从 FMP 抓取并计算
    logger.info("etf_heatmap_cache_miss", granularity=granularity, days=days)
    data = build_heatmap_data(granularity=granularity, days=days)

    # 写入缓存
    await set_heatmap_cache(redis, granularity, days, data)

    return data
```

- [ ] **Step 2: 在 app/api/v1/api.py 中挂载 etf_router**

将文件替换为：

```python
"""API v1 router configuration."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chatbot import router as chatbot_router
from app.api.v1.etf import router as etf_router
from app.core.logging import logger

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
api_router.include_router(etf_router, prefix="/etf", tags=["etf"])


@api_router.get("/health")
async def health_check():
    logger.info("health_check_called")
    return {"status": "healthy", "version": "1.0.0"}


@api_router.get("/hello")
async def hello():
    return {"deepalpha-club-ai": True}
```

- [ ] **Step 3: 写端点测试（追加到 tests/test_etf_heatmap.py）**

```python
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.cache.client import get_redis
from app.schemas.etf import HeatmapResponse, HeatmapSectorGroup, HeatmapETFRow, HeatmapCell


def _mock_heatmap_response() -> HeatmapResponse:
    return HeatmapResponse(
        granularity="day",
        days=5,
        date_labels=["2026-04-28"],
        sectors=[
            HeatmapSectorGroup(
                sector="01 信息技术",
                avg_cells=[HeatmapCell(date="2026-04-28", intensity=0.5)],
                etfs=[
                    HeatmapETFRow(
                        symbol="XLK",
                        name="科技行业精选指数ETF-SPDR",
                        cells=[HeatmapCell(date="2026-04-28", intensity=1.2)],
                    )
                ],
            )
        ],
    )


def test_heatmap_endpoint_returns_cached_data():
    mock_redis = AsyncMock()

    async def override_redis():
        yield mock_redis

    with patch("app.cache.etf_cache.get_heatmap_cache", return_value=_mock_heatmap_response()):
        app.dependency_overrides[get_redis] = override_redis
        client = TestClient(app)
        response = client.get("/api/v1/etf/heatmap?granularity=day&days=5")
        assert response.status_code == 200
        data = response.json()
        assert data["granularity"] == "day"
        assert len(data["sectors"]) == 1
        app.dependency_overrides.clear()


def test_heatmap_endpoint_invalid_granularity():
    mock_redis = AsyncMock()

    async def override_redis():
        yield mock_redis

    app.dependency_overrides[get_redis] = override_redis
    client = TestClient(app)
    response = client.get("/api/v1/etf/heatmap?granularity=invalid")
    assert response.status_code == 422
    app.dependency_overrides.clear()
```

- [ ] **Step 4: 运行所有 ETF 相关测试**

```bash
uv run pytest tests/test_etf_heatmap.py -v
```

预期：全部 PASS（端点测试、schema 测试、计算函数测试）

- [ ] **Step 5: 提交**

```bash
git add app/api/v1/etf.py app/api/v1/api.py tests/test_etf_heatmap.py
git commit -m "feat: 创建 ETF heatmap 端点，挂载到 api_router"
```

---

## Task 5: 前端 API 客户端 + Zustand Store

**Files:**
- 新增: `frontend/lib/api/etf.ts`
- 新增: `frontend/lib/store/etf.ts`

- [ ] **Step 1: 创建 frontend/lib/api/etf.ts**

```typescript
// frontend/lib/api/etf.ts
import apiClient from './client'

export type Granularity = 'day' | 'week' | 'month'

export interface HeatmapCell {
  date: string
  intensity: number | null
}

export interface HeatmapETFRow {
  symbol: string
  name: string
  cells: HeatmapCell[]
}

export interface HeatmapSectorGroup {
  sector: string
  avg_cells: HeatmapCell[]
  etfs: HeatmapETFRow[]
}

export interface HeatmapResponse {
  granularity: Granularity
  days: number
  date_labels: string[]
  sectors: HeatmapSectorGroup[]
}

export const fetchETFHeatmap = async (
  granularity: Granularity = 'day',
  days: number = 30
): Promise<HeatmapResponse> => {
  const response = await apiClient.get<HeatmapResponse>('/api/v1/etf/heatmap', {
    params: { granularity, days },
  })
  return response.data
}
```

- [ ] **Step 2: 创建 frontend/lib/store/etf.ts**

```typescript
// frontend/lib/store/etf.ts
import { create } from 'zustand'
import type { Granularity } from '@/lib/api/etf'

interface ETFState {
  granularity: Granularity
  days: number
  setGranularity: (g: Granularity) => void
}

export const useETFStore = create<ETFState>((set) => ({
  granularity: 'day',
  days: 30,
  setGranularity: (granularity) => set({ granularity }),
}))
```

- [ ] **Step 3: TypeScript 类型检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误

- [ ] **Step 4: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/lib/api/etf.ts frontend/lib/store/etf.ts
git commit -m "feat: ETF 前端 API 客户端 + Zustand store"
```

---

## Task 6: 创建 GranularityToggle 组件

**Files:**
- 新增: `frontend/components/etf/GranularityToggle.tsx`

- [ ] **Step 1: 创建目录和组件**

```bash
mkdir -p /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend/components/etf
```

```typescript
// frontend/components/etf/GranularityToggle.tsx
'use client'

import type { Granularity } from '@/lib/api/etf'

interface GranularityToggleProps {
  value: Granularity
  onChange: (g: Granularity) => void
  disabled?: boolean
}

const OPTIONS: { value: Granularity; label: string }[] = [
  { value: 'day', label: '日' },
  { value: 'week', label: '周' },
  { value: 'month', label: '月' },
]

export default function GranularityToggle({ value, onChange, disabled }: GranularityToggleProps) {
  return (
    <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-0.5">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(opt.value)}
          className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors disabled:opacity-50 ${
            value === opt.value
              ? 'bg-white shadow-sm text-gray-900'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: TypeScript 检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/components/etf/GranularityToggle.tsx
git commit -m "feat: GranularityToggle 组件（日/周/月切换）"
```

---

## Task 7: 创建 ETFHeatmapTable 组件

**Files:**
- 新增: `frontend/components/etf/ETFHeatmapTable.tsx`

- [ ] **Step 1: 创建组件**

```typescript
// frontend/components/etf/ETFHeatmapTable.tsx
'use client'

import { useState } from 'react'
import type { HeatmapResponse, HeatmapCell } from '@/lib/api/etf'

interface ETFHeatmapTableProps {
  data: HeatmapResponse
}

// intensity → 背景色（红=流入, 绿=流出）
function intensityStyle(intensity: number | null): React.CSSProperties {
  if (intensity === null) return { backgroundColor: '#f9fafb' }
  const alpha = Math.min(Math.abs(intensity) / 3, 1)
  const color =
    intensity > 0
      ? `rgba(239, 68, 68, ${alpha})`   // red-500
      : `rgba(34, 197, 94, ${alpha})`   // green-500
  return { backgroundColor: color }
}

function Cell({ cell }: { cell: HeatmapCell }) {
  return (
    <td
      className="px-2 py-1.5 text-center text-xs font-mono whitespace-nowrap border-r border-gray-100 min-w-[72px]"
      style={intensityStyle(cell.intensity)}
    >
      {cell.intensity !== null ? cell.intensity.toFixed(2) : '—'}
    </td>
  )
}

export default function ETFHeatmapTable({ data }: ETFHeatmapTableProps) {
  const [expandedSectors, setExpandedSectors] = useState<Set<string>>(new Set())

  const toggleSector = (sector: string) => {
    setExpandedSectors((prev) => {
      const next = new Set(prev)
      if (next.has(sector)) {
        next.delete(sector)
      } else {
        next.add(sector)
      }
      return next
    })
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
      <table className="border-collapse text-sm" style={{ minWidth: `${280 + data.date_labels.length * 72}px` }}>
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            {/* 固定列 */}
            <th className="sticky left-0 z-20 bg-gray-50 px-4 py-2.5 text-left font-semibold text-gray-700 border-r border-gray-200 min-w-[200px]">
              板块/ETF
            </th>
            <th className="sticky left-[200px] z-20 bg-gray-50 px-3 py-2.5 text-left font-semibold text-gray-700 border-r border-gray-200 min-w-[80px]">
              Ticker
            </th>
            {/* 日期列 */}
            {data.date_labels.map((label) => (
              <th
                key={label}
                className="px-2 py-2.5 text-center font-medium text-gray-500 border-r border-gray-100 min-w-[72px] whitespace-nowrap"
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.sectors.map((sector) => {
            const isExpanded = expandedSectors.has(sector.sector)
            return (
              <>
                {/* 板块汇总行 */}
                <tr
                  key={sector.sector}
                  className="border-b border-gray-200 cursor-pointer hover:bg-gray-50 transition-colors"
                  onClick={() => toggleSector(sector.sector)}
                >
                  <td className="sticky left-0 z-10 bg-white px-4 py-2 font-semibold text-gray-800 border-r border-gray-200">
                    <span className="mr-2 text-gray-400 text-xs">
                      {isExpanded ? '▼' : '▶'}
                    </span>
                    {sector.sector}
                  </td>
                  <td className="sticky left-[200px] z-10 bg-white px-3 py-2 text-gray-400 text-xs border-r border-gray-200">
                    {sector.etfs.length} 只
                  </td>
                  {sector.avg_cells.map((cell) => (
                    <Cell key={cell.date} cell={cell} />
                  ))}
                </tr>

                {/* ETF 明细行 */}
                {isExpanded &&
                  sector.etfs.map((etf) => (
                    <tr
                      key={etf.symbol}
                      className="border-b border-gray-100 hover:bg-gray-50 transition-colors"
                    >
                      <td className="sticky left-0 z-10 bg-white px-4 py-1.5 text-gray-600 text-xs border-r border-gray-200 pl-8 truncate max-w-[200px]">
                        {etf.name}
                      </td>
                      <td className="sticky left-[200px] z-10 bg-white px-3 py-1.5 text-gray-700 font-mono text-xs font-medium border-r border-gray-200">
                        {etf.symbol}
                      </td>
                      {etf.cells.map((cell) => (
                        <Cell key={cell.date} cell={cell} />
                      ))}
                    </tr>
                  ))}
              </>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 2: TypeScript 检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/components/etf/ETFHeatmapTable.tsx
git commit -m "feat: ETFHeatmapTable 热力图表格（折叠分组 + 红绿着色 + 横向滚动）"
```

---

## Task 8: 更新 ETF 页面

**Files:**
- 修改: `frontend/app/(dashboard)/etf/page.tsx`

- [ ] **Step 1: 完整替换 frontend/app/(dashboard)/etf/page.tsx**

```typescript
// frontend/app/(dashboard)/etf/page.tsx
'use client'

import { useEffect, useState } from 'react'
import { fetchETFHeatmap, HeatmapResponse, Granularity } from '@/lib/api/etf'
import { useETFStore } from '@/lib/store/etf'
import GranularityToggle from '@/components/etf/GranularityToggle'
import ETFHeatmapTable from '@/components/etf/ETFHeatmapTable'

export default function ETFPage() {
  const { granularity, days, setGranularity } = useETFStore()
  const [data, setData] = useState<HeatmapResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async (g: Granularity) => {
    setLoading(true)
    setError('')
    try {
      const result = await fetchETFHeatmap(g, days)
      setData(result)
    } catch {
      setError('数据加载失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(granularity)
  }, [granularity])

  const handleGranularityChange = (g: Granularity) => {
    setGranularity(g)
  }

  return (
    <div>
      {/* 页头 */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">ETF 资金流</h1>
        <GranularityToggle
          value={granularity}
          onChange={handleGranularityChange}
          disabled={loading}
        />
      </div>

      {/* 说明文字 */}
      <p className="text-sm text-gray-500 mb-4">
        资金流强度基于 CLV × 价格 × 成交量计算，经 Z-score 标准化。
        红色表示资金流入，绿色表示资金流出，颜色越深强度越大。
      </p>

      {/* 错误状态 */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
          <span className="text-sm text-red-600">{error}</span>
          <button
            onClick={() => load(granularity)}
            className="text-sm text-red-600 font-medium hover:text-red-800 underline"
          >
            重试
          </button>
        </div>
      )}

      {/* 加载骨架 */}
      {loading && !data && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-10 border-b border-gray-100 animate-pulse bg-gray-50" />
          ))}
        </div>
      )}

      {/* 热力图表格 */}
      {data && (
        <div className={loading ? 'opacity-60 pointer-events-none' : ''}>
          <ETFHeatmapTable data={data} />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: TypeScript 检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误

- [ ] **Step 3: ESLint 检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx eslint . --ext .ts,.tsx --max-warnings 0
```

预期：无错误无警告

- [ ] **Step 4: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add "frontend/app/(dashboard)/etf/page.tsx"
git commit -m "feat: ETF 页面——热力图表格 + 粒度切换 + 加载/错误状态"
```

---

## Task 9: 手动集成验证

- [ ] **Step 1: 启动后端**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
uv run uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: 测试 heatmap 端点**

```bash
curl "http://localhost:8000/api/v1/etf/heatmap?granularity=day&days=5" | python3 -m json.tool | head -50
```

预期：返回包含 `sectors`、`date_labels`、`granularity` 的 JSON，sectors 数组有 12 个板块。

- [ ] **Step 3: 启动前端**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npm run dev
```

- [ ] **Step 4: 浏览器验证**

访问 `http://localhost:3000/dashboard`，登录后点击 **ETF 资金流**，验证：
- [ ] 表格正常加载，显示 12 个板块
- [ ] 默认折叠状态，点击板块行展开 ETF 明细
- [ ] 单元格颜色正确（红色=正数，绿色=负数）
- [ ] 切换 **周** / **月** 粒度，表格数据更新
- [ ] 切换粒度期间按钮禁用，旧数据半透明不闪烁

- [ ] **Step 5: 停止服务，最终提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add .
git status  # 确认无意外文件
git commit -m "docs: ETF 热力图功能验证完成" --allow-empty
```
