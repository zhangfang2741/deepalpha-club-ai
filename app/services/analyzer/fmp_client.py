"""Financial Modeling Prep (FMP) client for enhanced financial data.

This module provides comprehensive financial data from FMP including:
- Financial statements (Income, Balance Sheet, Cash Flow)
- Valuation metrics (PE, PS, EV/EBITDA, etc.)
- Stock quotes and market data
- Company profile and information

All data is traceable with source attribution.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.analysis import DataPoint, DataSource


# FMP API base URL (stable API as of Sep 2025)
_FMP_BASE_URL = "https://financialmodelingprep.com/stable"


class FmpClient:
    """Client for Financial Modeling Prep API with source attribution."""

    def __init__(self):
        self.base_url = _FMP_BASE_URL
        self.api_key = settings.FMP_API_KEY or "demo"
        self._cache: Dict[str, Any] = {}

    async def _fetch(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Fetch data from FMP API with caching.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            API response data
        """
        cache_key = f"{endpoint}:{str(params)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{self.base_url}/{endpoint}"
        query_params = {"apikey": self.api_key}
        if params:
            query_params.update(params)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, params=query_params)
                
                # Handle 401 Unauthorized - likely demo key limitations
                if resp.status_code == 401:
                    logger.warning(
                        "fmp_api_unauthorized",
                        endpoint=endpoint,
                        message="FMP API key is invalid or expired. Please configure a valid API key."
                    )
                    return []
                
                resp.raise_for_status()
                data = resp.json()
                self._cache[cache_key] = data
                return data
        except Exception as e:
            logger.exception("fmp_api_fetch_failed", endpoint=endpoint, error=str(e))
            return []

    async def get_company_profile(self, ticker: str) -> Dict[str, Any]:
        """Get company profile information.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Company profile data
        """
        return await self._fetch("profile", {"symbol": ticker})

    async def get_income_statement(
        self,
        ticker: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get income statement data.

        Args:
            ticker: Stock ticker symbol
            limit: Number of periods to fetch

        Returns:
            List of income statement records
        """
        return await self._fetch("income-statement", {"symbol": ticker, "limit": limit})

    async def get_balance_sheet(
        self,
        ticker: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get balance sheet data.

        Args:
            ticker: Stock ticker symbol
            limit: Number of periods to fetch

        Returns:
            List of balance sheet records
        """
        return await self._fetch("balance-sheet-statement", {"symbol": ticker, "limit": limit})

    async def get_cash_flow(
        self,
        ticker: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get cash flow statement data.

        Args:
            ticker: Stock ticker symbol
            limit: Number of periods to fetch

        Returns:
            List of cash flow statement records
        """
        return await self._fetch("cash-flow-statement", {"symbol": ticker, "limit": limit})

    async def get_key_metrics(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get key financial metrics.

        Args:
            ticker: Stock ticker symbol
            limit: Number of periods to fetch

        Returns:
            List of key metrics records
        """
        return await self._fetch("key-metrics", {"symbol": ticker, "limit": limit})

    async def get_financial_ratios(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get financial ratios.

        Args:
            ticker: Stock ticker symbol
            limit: Number of periods to fetch

        Returns:
            List of financial ratio records
        """
        return await self._fetch("ratios", {"symbol": ticker, "limit": limit})

    async def get_valuation_metrics(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get valuation metrics.

        Args:
            ticker: Stock ticker symbol
            limit: Number of periods to fetch

        Returns:
            List of valuation metrics records
        """
        return await self._fetch("valuation", {"symbol": ticker, "limit": limit})

    async def get_price_data(self, ticker: str) -> Dict[str, Any]:
        """Get current stock price and market data.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Current price data
        """
        quotes = await self._fetch("quote", {"symbol": ticker})
        return quotes[0] if quotes else {}

    def _extract_data_points(
        self,
        ticker: str,
        data: List[Dict[str, Any]],
        label_prefix: str,
    ) -> List[DataPoint]:
        """Extract DataPoints from API response.

        Args:
            ticker: Stock ticker symbol
            data: API response data
            label_prefix: Label prefix for data points

        Returns:
            List of DataPoints with source attribution
        """
        data_points: List[DataPoint] = []

        if not data or not isinstance(data, list):
            return data_points

        # Use the most recent period
        latest = data[0]
        period_date = latest.get("date", latest.get("calendarYear", "Unknown"))

        for key, value in latest.items():
            if key in ("date", "symbol", "calendarYear", "period", "filingDate"):
                continue

            if isinstance(value, (int, float)) and value != 0:
                # Format large numbers
                if abs(value) >= 1_000_000_000:
                    display_value = f"${value / 1_000_000_000:.2f}B"
                elif abs(value) >= 1_000_000:
                    display_value = f"${value / 1_000_000:.2f}M"
                elif abs(value) >= 1_000:
                    display_value = f"${value / 1_000:.2f}K"
                else:
                    display_value = f"{value:.2f}"

                # Format label
                label = key.replace(" ", "_").replace("/", "_")
                display_label = label_prefix + " " + label

                data_points.append(DataPoint(
                    value=display_value,
                    label=display_label,
                    source=DataSource.FMP.value,
                    url=f"https://site.financialmodelingprep.com/financial-statements/{ticker}",
                    fetched_at=datetime.utcnow(),
                ))

        return data_points

    async def get_all_financial_data(self, ticker: str) -> Dict[str, Any]:
        """Get all financial data for a company.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Complete financial data with source attribution
        """
        logger.info("fmp_data_fetch_started", ticker=ticker)

        results = {
            "ticker": ticker.upper(),
            "source": DataSource.FMP.value,
            "profile": {},
            "data_points": [],
            "analysis_timestamp": datetime.utcnow().isoformat(),
        }

        # Fetch company profile
        profile = await self.get_company_profile(ticker)
        if profile:
            results["profile"] = profile[0] if isinstance(profile, list) else profile

            # Add company info as data points
            if isinstance(profile, list) and profile:
                p = profile[0]
                for field in ["companyName", "industry", "sector", "description"]:
                    if field in p:
                        results["data_points"].append(DataPoint(
                            value=str(p[field]),
                            label=field,
                            source=DataSource.FMP.value,
                            url=f"https://site.financialmodelingprep.com/financial-statements/{ticker}",
                            fetched_at=datetime.utcnow(),
                        ))

        # Fetch income statement
        income = await self.get_income_statement(ticker, limit=1)
        income_points = self._extract_data_points(ticker, income, "Income")
        results["data_points"].extend(income_points)

        # Fetch balance sheet
        balance = await self.get_balance_sheet(ticker, limit=1)
        balance_points = self._extract_data_points(ticker, balance, "Balance")
        results["data_points"].extend(balance_points)

        # Fetch cash flow
        cash_flow = await self.get_cash_flow(ticker, limit=1)
        cf_points = self._extract_data_points(ticker, cash_flow, "CashFlow")
        results["data_points"].extend(cf_points)

        # Fetch key metrics
        metrics = await self.get_key_metrics(ticker, limit=1)
        metric_points = self._extract_data_points(ticker, metrics, "Metric")
        results["data_points"].extend(metric_points)

        # Fetch financial ratios
        ratios = await self.get_financial_ratios(ticker, limit=1)
        ratio_points = self._extract_data_points(ticker, ratios, "Ratio")
        results["data_points"].extend(ratio_points)

        # Fetch price data
        price = await self.get_price_data(ticker)
        if price:
            results["price_data"] = price
            for field in ["price", "marketCap", "pe", "eps", "dividendYield"]:
                if field in price and price[field]:
                    results["data_points"].append(DataPoint(
                        value=price[field],
                        label=f"Market_{field}",
                        source=DataSource.FMP.value,
                        url=f"https://site.financialmodelingprep.com/financial-statements/{ticker}",
                        fetched_at=datetime.utcnow(),
                    ))

        logger.info(
            "fmp_data_fetch_completed",
            ticker=ticker,
            data_points=len(results["data_points"]),
        )

        return results


# Singleton instance
fmp_client = FmpClient()