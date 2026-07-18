"""FMP 数据查询工具测试（monkeypatch FmpClient，无网络依赖）。"""

import pytest

from app.core.langgraph.tools import fmp_data


class _FakeFmpClient:
    """返回固定样例数据的假 FmpClient。"""

    async def get_price_data(self, ticker):
        return {
            "symbol": "NVDA",
            "name": "NVIDIA Corporation",
            "price": 164.2,
            "changePercentage": 1.35,
            "marketCap": 4_010_000_000_000,
            "pe": 51.3,
            "eps": 3.2,
            "volume": 210_000_000,
            "dayLow": 160.1,
            "dayHigh": 166.4,
            "yearLow": 86.6,
            "yearHigh": 174.0,
            "priceAvg50": 150.2,
            "priceAvg200": 130.5,
            "exchange": "NASDAQ",
        }

    async def get_company_profile(self, ticker):
        return [
            {
                "companyName": "NVIDIA Corporation",
                "sector": "Technology",
                "industry": "Semiconductors",
                "marketCap": 4_010_000_000_000,
                "price": 164.2,
                "beta": 1.68,
                "ceo": "Jensen Huang",
                "fullTimeEmployees": "29600",
                "country": "US",
                "exchangeFullName": "NASDAQ Global Select",
                "website": "https://www.nvidia.com",
                "description": "NVIDIA designs GPUs. " * 40,
            }
        ]

    async def get_income_statement(self, ticker, limit=5):
        return [
            {"date": "2024-12", "revenue": 60_900_000_000, "netIncome": 30_000_000_000, "epsdiluted": 3.2},
            {"date": "2023-12", "revenue": 26_900_000_000, "netIncome": 9_700_000_000, "epsdiluted": 1.1},
        ]

    async def get_key_metrics(self, ticker, limit=5):
        return [{"freeCashFlowPerShare": 2.4, "enterpriseValue": 4_050_000_000_000}]

    async def get_financial_ratios(self, ticker, limit=5):
        return [
            {
                "priceToEarningsRatio": 51.3,
                "priceToBookRatio": 45.2,
                "grossProfitMargin": 0.75,
                "netProfitMargin": 0.49,
                "returnOnEquity": 0.91,
                "debtToEquityRatio": 0.22,
                "dividendYield": 0.0003,
            }
        ]


class _EmptyFmpClient:
    async def get_price_data(self, ticker):
        return {}

    async def get_company_profile(self, ticker):
        return []

    async def get_income_statement(self, ticker, limit=5):
        return []

    async def get_key_metrics(self, ticker, limit=5):
        return []

    async def get_financial_ratios(self, ticker, limit=5):
        return []


@pytest.fixture
def fake_client(monkeypatch):
    monkeypatch.setattr(fmp_data, "FmpClient", _FakeFmpClient)


@pytest.fixture
def empty_client(monkeypatch):
    monkeypatch.setattr(fmp_data, "FmpClient", _EmptyFmpClient)


async def test_fmp_quote(fake_client):
    out = await fmp_data.fmp_quote.ainvoke({"symbol": "nvda"})
    assert "NVDA 实时报价" in out
    assert "$4.01T" in out  # 市值格式化（万亿档）
    assert "51.30" in out  # PE
    assert "+1.35%" in out  # 涨跌幅
    assert "$86.6 – $174.0" in out  # 52周范围
    assert "数据来源：FMP" in out


async def test_fmp_company_profile(fake_client):
    out = await fmp_data.fmp_company_profile.ainvoke({"symbol": "NVDA"})
    assert "公司画像" in out
    assert "Semiconductors" in out
    assert "Jensen Huang" in out
    assert "简介" in out
    assert "…" in out  # 长简介被截断


async def test_fmp_financial_statement_income(fake_client):
    out = await fmp_data.fmp_financial_statement.ainvoke({"symbol": "NVDA", "statement": "income", "limit": 2})
    assert "利润表" in out
    assert "2024-12" in out and "2023-12" in out
    assert "营收" in out
    assert "$60.90B" in out


async def test_fmp_financial_statement_invalid():
    out = await fmp_data.fmp_financial_statement.ainvoke({"symbol": "NVDA", "statement": "xxx"})
    assert "无效" in out


async def test_fmp_key_metrics(fake_client):
    out = await fmp_data.fmp_key_metrics.ainvoke({"symbol": "NVDA"})
    assert "关键指标" in out
    assert "51.30" in out  # PE
    assert "75.00%" in out  # 毛利率
    assert "91.00%" in out  # ROE


async def test_empty_data_returns_hint(empty_client):
    out = await fmp_data.fmp_quote.ainvoke({"symbol": "ZZZZ"})
    assert "未获取到" in out
