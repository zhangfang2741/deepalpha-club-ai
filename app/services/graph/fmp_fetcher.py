"""FMP 电话会议记录获取服务。

使用 Financial Modeling Prep API 拉取电话会议文字记录，
返回可直接送入摄取流水线的文本内容。

优先级参考：earnings call > investor_relations
"""

from datetime import datetime
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import logger

_FMP_BASE_STABLE = "https://financialmodelingprep.com/stable"
_FMP_BASE_V3 = "https://financialmodelingprep.com/api/v3"


class FmpTranscriptFetcher:
    """FMP 电话会议记录客户端。"""

    def __init__(self):  # noqa: D107
        self.api_key = settings.FMP_API_KEY or "demo"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, url: str, params: Optional[dict] = None) -> dict | list:
        p = {"apikey": self.api_key}
        if params:
            p.update(params)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=p)
            if resp.status_code == 401:
                logger.warning("fmp_unauthorized", url=url)
                return []
            resp.raise_for_status()
            return resp.json()

    async def get_transcript(
        self,
        ticker: str,
        year: int,
        quarter: int,
    ) -> Optional[str]:
        """获取单季度电话会议文字记录。

        Args:
            ticker: 股票代码（如 NVDA）
            year: 年份（如 2024）
            quarter: 季度 1-4

        Returns:
            文字记录纯文本，或 None（未找到）
        """
        # stable 端点
        url = f"{_FMP_BASE_STABLE}/earning-call-transcript"
        try:
            data = await self._get(url, {"symbol": ticker.upper(), "year": year, "quarter": quarter})
            if isinstance(data, list) and data:
                return self._format_transcript(data[0], ticker, year, quarter)
        except Exception:
            pass

        # 回退到 v3 端点
        url_v3 = f"{_FMP_BASE_V3}/earning_call_transcript/{ticker.upper()}"
        try:
            data = await self._get(url_v3, {"year": year, "quarter": quarter})
            if isinstance(data, list) and data:
                return self._format_transcript(data[0], ticker, year, quarter)
        except Exception as e:
            logger.warning("fmp_transcript_fetch_failed", ticker=ticker, year=year, quarter=quarter, error=str(e))

        return None

    def _format_transcript(
        self,
        item: dict,
        ticker: str,
        year: int,
        quarter: int,
    ) -> str:
        """将 FMP 记录格式化为结构化文本，便于 LLM 抽取。"""
        date = item.get("date", "")
        content = item.get("content", "")
        symbol = item.get("symbol", ticker)

        header = (
            f"EARNINGS CALL TRANSCRIPT\n"
            f"Company: {symbol} | Date: {date} | Period: {year} Q{quarter}\n"
            f"{'=' * 60}\n\n"
        )
        return header + content

    async def get_recent_transcripts(
        self,
        ticker: str,
        quarters: int = 4,
    ) -> list[tuple[str, dict]]:
        """获取最近 N 个季度的电话会议记录。

        Args:
            ticker: 股票代码
            quarters: 获取季度数（最多 8）

        Returns:
            [(文字记录文本, 元信息字典), ...]
        """
        now = datetime.now()
        current_year = now.year
        current_quarter = (now.month - 1) // 3 + 1

        results: list[tuple[str, dict]] = []
        q, y = current_quarter, current_year

        for _ in range(min(quarters, 8)):
            text = await self.get_transcript(ticker, y, q)
            if text:
                results.append((
                    text,
                    {
                        "ticker": ticker.upper(),
                        "year": y,
                        "quarter": q,
                        "period": f"{y}-Q{q}",
                    },
                ))
            # 上一季度
            q -= 1
            if q == 0:
                q = 4
                y -= 1

        logger.info(
            "fmp_transcripts_fetched",
            ticker=ticker,
            requested=quarters,
            found=len(results),
        )
        return results

    async def list_available_transcripts(self, ticker: str) -> list[dict]:
        """列出该 ticker 所有可用的电话会议记录（年份+季度）。"""
        url = f"{_FMP_BASE_V3}/earning_call_transcript/{ticker.upper()}"
        try:
            data = await self._get(url)
            if isinstance(data, list):
                return [
                    {
                        "ticker": ticker.upper(),
                        "year": item.get("year"),
                        "quarter": item.get("quarter"),
                        "date": item.get("date", ""),
                    }
                    for item in data
                    if item.get("year") and item.get("quarter")
                ]
        except Exception as e:
            logger.warning("fmp_list_transcripts_failed", ticker=ticker, error=str(e))
        return []


# 单例
fmp_transcript_fetcher = FmpTranscriptFetcher()
