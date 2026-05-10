"""News client for fetching market news and sentiment.

This module provides news aggregation and sentiment analysis including:
- Company-specific news
- Industry news
- Market-wide news
- Sentiment scores

All data is traceable with source attribution.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.analysis import DataPoint, DataSource


# News API base URL
_NEWS_API_BASE = "https://newsapi.org/v2"
_NEWS_HEADERS = {
    "User-Agent": "DeepAlpha/1.0 (investment research)",
}


class NewsClient:
    """Client for news aggregation with sentiment analysis."""

    def __init__(self):
        self.news_api_key = settings.NEWS_API_KEY or ""
        self._cache: Dict[str, Any] = {}

    async def _fetch_news_api(self, endpoint: str, params: Dict[str, Any]) -> Any:
        """Fetch data from NewsAPI.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            API response data
        """
        if not self.news_api_key:
            logger.warning("news_api_key_not_configured")
            return {"articles": []}

        cache_key = f"{endpoint}:{str(params)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{_NEWS_API_BASE}/{endpoint}"
        params["apiKey"] = self.news_api_key

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, params=params, headers=_NEWS_HEADERS)
                resp.raise_for_status()
                data = resp.json()
                self._cache[cache_key] = data
                return data
        except Exception as e:
            logger.exception("news_api_fetch_failed", endpoint=endpoint, error=str(e))
            return {"articles": []}

    async def get_company_news(self, ticker: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get news articles for a company.

        Args:
            ticker: Stock ticker symbol
            days: Number of days to look back

        Returns:
            List of news articles
        """
        from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        data = await self._fetch_news_api(
            "everything",
            {
                "q": f'"{ticker}" OR "{ticker} stock"',
                "from": from_date,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 20,
            },
        )

        return data.get("articles", [])

    async def get_industry_news(self, industry: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get news articles for an industry.

        Args:
            industry: Industry name
            days: Number of days to look back

        Returns:
            List of news articles
        """
        from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        data = await self._fetch_news_api(
            "everything",
            {
                "q": f'"{industry}" industry',
                "from": from_date,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 10,
            },
        )

        return data.get("articles", [])

    async def get_market_news(self, days: int = 3) -> List[Dict[str, Any]]:
        """Get market-wide news articles.

        Args:
            days: Number of days to look back

        Returns:
            List of news articles
        """
        from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        data = await self._fetch_news_api(
            "top-headlines",
            {
                "category": "business",
                "country": "us",
                "from": from_date,
                "pageSize": 15,
            },
        )

        return data.get("articles", [])

    def _analyze_sentiment(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze sentiment of news articles.

        Simple keyword-based sentiment analysis.
        For production, consider using a dedicated ML model.

        Args:
            articles: List of news articles

        Returns:
            Sentiment analysis results
        """
        positive_keywords = [
            "gain", "growth", "surge", "rise", "beat", "exceed", "record",
            "profit", "bullish", "upgrade", "buy", "outperform", "strong",
        ]
        negative_keywords = [
            "loss", "decline", "drop", "fall", "miss", "below", "weak",
            "bearish", "downgrade", "sell", "underperform", "concern",
        ]

        scores = []
        positive_count = 0
        negative_count = 0

        for article in articles:
            text = (
                (article.get("title", "") + " " + article.get("description", ""))
                .lower()
            )

            pos_matches = sum(1 for kw in positive_keywords if kw in text)
            neg_matches = sum(1 for kw in negative_keywords if kw in text)

            if pos_matches > neg_matches:
                score = 0.6 + min((pos_matches - neg_matches) * 0.1, 0.3)
                positive_count += 1
            elif neg_matches > pos_matches:
                score = 0.4 - min((neg_matches - pos_matches) * 0.1, 0.3)
                negative_count += 1
            else:
                score = 0.5

            scores.append(score)

        avg_sentiment = sum(scores) / len(scores) if scores else 0.5

        # Convert to 0-100 scale
        sentiment_score = avg_sentiment * 100

        return {
            "average_sentiment": round(sentiment_score, 1),
            "sentiment_label": self._sentiment_label(sentiment_score),
            "article_count": len(articles),
            "positive_count": positive_count,
            "negative_count": negative_count,
            "neutral_count": len(articles) - positive_count - negative_count,
        }

    def _sentiment_label(self, score: float) -> str:
        """Convert sentiment score to label."""
        if score >= 70:
            return "Very Positive"
        elif score >= 60:
            return "Positive"
        elif score >= 40:
            return "Neutral"
        elif score >= 30:
            return "Negative"
        else:
            return "Very Negative"

    async def analyze_news_sentiment(
        self,
        ticker: str,
        industry: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform comprehensive news sentiment analysis.

        Args:
            ticker: Stock ticker symbol
            industry: Optional industry name

        Returns:
            Analysis results with source attribution
        """
        logger.info("news_sentiment_analysis_started", ticker=ticker)

        results = {
            "ticker": ticker.upper(),
            "source": DataSource.NEWS_API.value,
            "data_points": [],
            "company_news": [],
            "industry_news": [],
            "sentiment": {},
            "analysis_timestamp": datetime.utcnow().isoformat(),
        }

        # Get company news
        company_news = await self.get_company_news(ticker, days=7)
        if company_news:
            results["company_news"] = company_news[:10]  # Top 10

            # Add as data points
            results["data_points"].append(DataPoint(
                value=len(company_news),
                label="Company_News_Articles_7d",
                source=DataSource.NEWS_API.value,
                url="https://newsapi.org",
                fetched_at=datetime.utcnow(),
            ))

        # Get industry news if provided
        if industry:
            industry_news = await self.get_industry_news(industry, days=7)
            if industry_news:
                results["industry_news"] = industry_news[:5]

                results["data_points"].append(DataPoint(
                    value=len(industry_news),
                    label=f"Industry_News_Articles_7d_{industry}",
                    source=DataSource.NEWS_API.value,
                    url="https://newsapi.org",
                    fetched_at=datetime.utcnow(),
                ))

        # Analyze sentiment
        all_news = results["company_news"] + results["industry_news"]
        sentiment = self._analyze_sentiment(all_news)
        results["sentiment"] = sentiment

        # Add sentiment as data point
        results["data_points"].append(DataPoint(
            value=sentiment["average_sentiment"],
            label="News_Sentiment_Score",
            source=DataSource.NEWS_API.value,
            url="https://newsapi.org",
            fetched_at=datetime.utcnow(),
        ))

        logger.info(
            "news_sentiment_analysis_completed",
            ticker=ticker,
            sentiment=sentiment["average_sentiment"],
            articles=len(all_news),
        )

        return results


# Singleton instance
news_client = NewsClient()