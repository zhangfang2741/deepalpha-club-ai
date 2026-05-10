"""SEC EDGAR client for fetching financial filings.

This module provides methods to fetch SEC EDGAR filings including:
- 10-K (Annual reports)
- 10-Q (Quarterly reports)
- 8-K (Current reports)
- 13F (Institutional holdings)

All data is traceable with source attribution.
"""

import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import logger
from app.schemas.analysis import DataPoint, DataSource


# SEC EDGAR API endpoints
_EDGAR_BASE = "https://data.sec.gov/submissions"
_COMPANY_BASE = "https://www.sec.gov/cgi-bin/browse-edgar"
_HEADERS = {
    "User-Agent": "DeepAlpha/1.0 (investment research; mailto:research@deepalpha.ai)",
    "Accept-Encoding": "gzip, deflate",
}


class SecEdgarClient:
    """Client for SEC EDGAR filings with source attribution."""

    def __init__(self):
        self.base_url = _EDGAR_BASE
        self.headers = _HEADERS
        self._cache: Dict[str, Any] = {}

    async def _fetch(self, url: str) -> Dict[str, Any]:
        """Fetch JSON data from URL with caching and rate limiting."""
        if url in self._cache:
            return self._cache[url]

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=self.headers)
                resp.raise_for_status()
                data = resp.json()
                self._cache[url] = data
                # SEC requests: max 10 requests per second
                await asyncio.sleep(0.1)
                return data
        except Exception as e:
            logger.exception("sec_edgar_fetch_failed", url=url, error=str(e))
            raise

    def _cik_lookup(self, ticker: str) -> str:
        """Convert ticker to CIK number with zero-padding."""
        return ticker.ljust(10, "0")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def get_company_filings(self, ticker: str) -> Dict[str, Any]:
        """Get all filings for a company.

        Args:
            ticker: Stock ticker symbol (e.g., 'NVDA')

        Returns:
            Company filings metadata
        """
        cik = self._cik_lookup(ticker.upper())
        url = f"{_EDGAR_BASE}/CIK{cik}.json"
        return await self._fetch(url)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def get_latest_10k(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get the latest 10-K filing.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Latest 10-K filing metadata or None
        """
        filings = await self.get_company_filings(ticker)
        recent = filings.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        document_urls = recent.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form == "10-K":
                return {
                    "form": form,
                    "filingDate": filing_dates[i],
                    "accessionNumber": accession_numbers[i],
                    "documentUrl": document_urls[i],
                    "ticker": ticker.upper(),
                }

        return None

    async def get_financial_data(
        self,
        ticker: str,
        years: int = 3,
    ) -> List[DataPoint]:
        """Extract key financial metrics from 10-K filings.

        Args:
            ticker: Stock ticker symbol
            years: Number of years of data to fetch

        Returns:
            List of DataPoints with source attribution
        """
        data_points: List[DataPoint] = []
        cik = self._cik_lookup(ticker.upper())

        try:
            # Fetch company facts for financial data
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            facts = await self._fetch(url)

            # Key metrics to extract
            metrics = [
                ("Revenues", "Revenue"),
                ("NetIncomeLoss", "Net Income"),
                ("Assets", "Total Assets"),
                ("Liabilities", "Total Liabilities"),
                ("StockholdersEquity", "Shareholders Equity"),
                ("GrossProfit", "Gross Profit"),
                ("OperatingIncomeLoss", "Operating Income"),
                ("EarningsPerShare", "EPS"),
            ]

            us_gaap = facts.get("facts", {}).get("us-gaap", {})

            for concept_name, label in metrics:
                if concept_name in us_gaap:
                    concept = us_gaap[concept_name]
                    units = concept.get("units", {})

                    # Try USD (in millions) first
                    if "USD" in units:
                        values = units["USD"]
                        if isinstance(values, list) and values:
                            # Get most recent value
                            latest = values[-1]
                            data_points.append(DataPoint(
                                value=latest.get("val"),
                                label=f"{label} (Latest)",
                                source=DataSource.SEC_EDGAR.value,
                                url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K",
                                fetched_at=datetime.utcnow(),
                            ))

            logger.info(
                "sec_financial_data_extracted",
                ticker=ticker,
                metric_count=len(data_points),
            )

        except Exception as e:
            logger.exception("sec_financial_extract_failed", ticker=ticker, error=str(e))

        return data_points

    async def get_institutional_holdings(self, ticker: str) -> List[DataPoint]:
        """Get 13F institutional holdings for the company.

        Args:
            ticker: Stock ticker symbol

        Returns:
            List of DataPoints with source attribution
        """
        data_points: List[DataPoint] = []
        cik = self._cik_lookup(ticker.upper())

        try:
            # Get company info for 13F holdings
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            facts = await self._fetch(url)

            # Check for 13F holdings info
            # Note: Full 13F parsing requires XBRL parsing which is complex
            # For now, we return metadata about available 13F filings

            filings = await self.get_company_filings(ticker)
            recent = filings.get("filings", {}).get("recent", {})

            form_13f_count = sum(1 for f in recent.get("form", []) if "13F" in f)

            data_points.append(DataPoint(
                value=f"13F filings available: {form_13f_count}",
                label="13F Institutional Holdings",
                source=DataSource.SEC_EDGAR.value,
                url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=13F",
                fetched_at=datetime.utcnow(),
            ))

        except Exception as e:
            logger.exception("sec_13f_fetch_failed", ticker=ticker, error=str(e))

        return data_points

    async def analyze_company(self, ticker: str) -> Dict[str, Any]:
        """Perform comprehensive SEC EDGAR analysis.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Analysis results with source attribution
        """
        logger.info("sec_edgar_analysis_started", ticker=ticker)

        results = {
            "ticker": ticker.upper(),
            "source": DataSource.SEC_EDGAR.value,
            "data_points": [],
            "latest_10k": None,
            "analysis_timestamp": datetime.utcnow().isoformat(),
        }

        # Get latest 10-K
        latest_10k = await self.get_latest_10k(ticker)
        if latest_10k:
            results["latest_10k"] = latest_10k

        # Get financial data
        financial_data = await self.get_financial_data(ticker)
        results["data_points"].extend(financial_data)

        # Get institutional holdings info
        holdings_data = await self.get_institutional_holdings(ticker)
        results["data_points"].extend(holdings_data)

        logger.info(
            "sec_edgar_analysis_completed",
            ticker=ticker,
            data_points=len(results["data_points"]),
        )

        return results


# Singleton instance
sec_edgar_client = SecEdgarClient()