"""多源电话会议记录抓取服务。

级联抓取顺序（按优先级）：
1. Alpha Vantage API
2. Motley Fool 搜索 + 正文抓取
3. SEC EDGAR 8-K 附件扫描

全部失败时返回 None。
"""

import re
from html.parser import HTMLParser
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import logger

_ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"
_FOOL_SEARCH_BASE = "https://www.fool.com/search/solr.aspx"
_FOOL_BASE = "https://www.fool.com"
_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class _HTMLTextExtractor(HTMLParser):
    """剥离 HTML 标签，保留纯文本。"""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_tags = {"script", "style", "head", "meta", "link", "noscript"}
        self._current_skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._skip_tags:
            self._current_skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._skip_tags:
            self._current_skip = max(0, self._current_skip - 1)

    def handle_data(self, data):
        if self._current_skip == 0:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _html_to_text(html: str) -> str:
    """将 HTML 内容转换为纯文本（去噪声）。"""
    parser = _HTMLTextExtractor()
    parser.feed(html)
    text = parser.get_text()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class _ArticleExtractor(HTMLParser):
    """从 HTML 中提取文章正文（优先 <article> 或特定 class 的 div）。"""

    _TARGET_CLASSES = {"article-body", "article-content", "transcript"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._in_target = 0
        self._depth_stack: list[bool] = []
        self._skip_tags = {"script", "style", "noscript"}
        self._skip_depth = 0

    def _is_target_tag(self, tag: str, attrs: list) -> bool:
        if tag.lower() == "article":
            return True
        if tag.lower() == "div":
            attr_dict = dict(attrs)
            class_val = attr_dict.get("class", "")
            for cls in self._TARGET_CLASSES:
                if cls in class_val:
                    return True
        return False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._skip_tags:
            self._skip_depth += 1
            self._depth_stack.append(False)
            return
        is_target = self._is_target_tag(tag, attrs)
        if is_target:
            self._in_target += 1
        self._depth_stack.append(is_target)

    def handle_endtag(self, tag):
        if tag.lower() in self._skip_tags:
            self._skip_depth = max(0, self._skip_depth - 1)
            if self._depth_stack:
                self._depth_stack.pop()
            return
        if self._depth_stack:
            was_target = self._depth_stack.pop()
            if was_target:
                self._in_target = max(0, self._in_target - 1)

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        if self._in_target > 0:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _extract_article_text(html: str) -> str:
    """尝试提取文章正文，失败时回退到全量 HTML 转文本。"""
    extractor = _ArticleExtractor()
    extractor.feed(html)
    text = extractor.get_text().strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) >= 200:
        return text
    # 回退：全量 HTML 转文本
    return _html_to_text(html)


def _format_transcript(ticker: str, year: int, quarter: int, source: str, content: str) -> str:
    """将文字记录格式化为结构化文本，与 fmp_fetcher 输出风格一致。"""
    header = (
        f"EARNINGS CALL TRANSCRIPT\n"
        f"Company: {ticker.upper()} | Source: {source} | Period: {year} Q{quarter}\n"
        f"{'=' * 60}\n\n"
    )
    return header + content


class TranscriptScraper:
    """多源电话会议记录抓取器，按优先级级联。"""

    def __init__(self):  # noqa: D107
        self.alpha_vantage_key = settings.ALPHA_VANTAGE_KEY or "demo"

    # ------------------------------------------------------------------ #
    # Source 1: Alpha Vantage                                              #
    # ------------------------------------------------------------------ #

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    async def _fetch_alpha_vantage(self, ticker: str, year: int, quarter: int) -> Optional[str]:
        """调用 Alpha Vantage 电话会议转录 API。"""
        params = {
            "function": "EARNINGS_CALL_TRANSCRIPT",
            "symbol": ticker.upper(),
            "quarter": f"{year}Q{quarter}",
            "apikey": self.alpha_vantage_key,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(_ALPHA_VANTAGE_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        transcript_items = data.get("transcript", [])
        if not transcript_items:
            return None

        lines = [f"{item.get('name', '')}: {item.get('content', '')}" for item in transcript_items]
        text = "\n\n".join(line for line in lines if line.strip())
        if len(text) > 500:
            return text
        return None

    # ------------------------------------------------------------------ #
    # Source 2: Motley Fool                                                #
    # ------------------------------------------------------------------ #

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    async def _fetch_motley_fool(self, ticker: str, year: int, quarter: int) -> Optional[str]:
        """通过 Motley Fool 搜索并抓取电话会议记录页面。"""
        q = f"{ticker} Q{quarter} {year} earnings call transcript"
        params = {
            "q": q,
            "categories": "13",
            "page": "1",
        }
        async with httpx.AsyncClient(timeout=30, headers=_BROWSER_HEADERS) as client:
            # 1. 搜索
            search_resp = await client.get(_FOOL_SEARCH_BASE, params=params)
            search_resp.raise_for_status()
            search_data = search_resp.json()

            results = search_data.get("solrResults", {}).get("results", [])
            target_url: Optional[str] = None
            ticker_lower = ticker.lower()
            for item in results:
                url = item.get("url", "")
                if "transcript" in url and ticker_lower in url:
                    target_url = url
                    break

            if not target_url:
                return None

            if target_url.startswith("/"):
                target_url = _FOOL_BASE + target_url

            # 2. 抓取正文
            page_resp = await client.get(target_url)
            page_resp.raise_for_status()
            text = _extract_article_text(page_resp.text)

        if len(text) > 500:
            return text
        return None

    # ------------------------------------------------------------------ #
    # Source 3: SEC EDGAR 8-K 附件扫描                                     #
    # ------------------------------------------------------------------ #

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    async def _fetch_sec_8k(self, ticker: str, year: Optional[int], quarter: Optional[int]) -> Optional[str]:
        """扫描 SEC EDGAR 8-K 附件，查找电话会议记录或业绩新闻稿。"""
        from app.services.graph.sec_fetcher import sec_fetcher

        meta = await sec_fetcher.get_submissions_meta(ticker)
        if not meta:
            return None

        recent = meta.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accs = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])
        cik_raw = str(meta.get("cik", "")).lstrip("0")

        scanned = 0
        for i, form in enumerate(forms):
            if form not in ("8-K", "8-K/A"):
                continue
            if scanned >= 15:
                break
            scanned += 1

            filing_date = dates[i] if i < len(dates) else ""
            # 年份过滤：若指定了年份，只看对应年份（Q1 允许上一年）
            if year is not None:
                year_str = str(year)
                prev_year_str = str(year - 1)
                if not filing_date.startswith(year_str):
                    if quarter == 1 and filing_date.startswith(prev_year_str):
                        pass  # 允许
                    else:
                        continue

            acc = accs[i] if i < len(accs) else ""
            if not acc:
                continue

            acc_no_dashes = acc.replace("-", "")
            index_url = f"{_ARCHIVES_BASE}/{cik_raw}/{acc_no_dashes}/{acc}-index.json"

            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    idx_resp = await client.get(
                        index_url,
                        headers={"User-Agent": "DeepAlpha/1.0 (investment research; mailto:research@deepalpha.ai)"},
                    )
                    idx_resp.raise_for_status()
                    idx_data = idx_resp.json()
            except Exception as e:
                logger.warning("sec_8k_index_fetch_failed", acc=acc, error=str(e))
                continue

            items = idx_data.get("directory", {}).get("item", [])

            transcript_doc: Optional[str] = None
            press_release_doc: Optional[str] = None

            for doc_item in items:
                name = doc_item.get("name", "").lower()
                desc = doc_item.get("description", "").lower()
                combined = name + " " + desc

                doc_href = doc_item.get("name", "")
                doc_url = f"{_ARCHIVES_BASE}/{cik_raw}/{acc_no_dashes}/{doc_href}"

                if transcript_doc is None:
                    if any(kw in combined for kw in ("transcript", "prepared remarks", "earnings call")):
                        transcript_doc = doc_url

                if press_release_doc is None:
                    if any(kw in combined for kw in ("press release", "earnings release", "ex-99", "ex99")):
                        press_release_doc = doc_url

            chosen_url = transcript_doc or press_release_doc
            if not chosen_url:
                continue

            text = await sec_fetcher.fetch_document_text(chosen_url)
            if len(text) > 300:
                return text

        return None

    # ------------------------------------------------------------------ #
    # 公开入口                                                              #
    # ------------------------------------------------------------------ #

    async def get_transcript(
        self,
        ticker: str,
        year: int,
        quarter: int,
    ) -> Optional[str]:
        """依次尝试三个数据源，返回格式化的电话会议记录文本。

        Args:
            ticker: 股票代码（如 NVDA）
            year: 年份（如 2024）
            quarter: 季度 1-4

        Returns:
            带 header 的格式化文本，或 None（全部失败）
        """
        # Source 1: Alpha Vantage
        try:
            text = await self._fetch_alpha_vantage(ticker, year, quarter)
            if text:
                logger.info("transcript_source_success", ticker=ticker, year=year, quarter=quarter, source="alpha_vantage")
                return _format_transcript(ticker, year, quarter, "Alpha Vantage", text)
        except Exception as e:
            logger.warning("alpha_vantage_transcript_failed", ticker=ticker, year=year, quarter=quarter, error=str(e))

        # Source 2: Motley Fool
        try:
            text = await self._fetch_motley_fool(ticker, year, quarter)
            if text:
                logger.info("transcript_source_success", ticker=ticker, year=year, quarter=quarter, source="motley_fool")
                return _format_transcript(ticker, year, quarter, "Motley Fool", text)
        except Exception as e:
            logger.warning("motley_fool_transcript_failed", ticker=ticker, year=year, quarter=quarter, error=str(e))

        # Source 3: SEC EDGAR 8-K
        try:
            text = await self._fetch_sec_8k(ticker, year, quarter)
            if text:
                logger.info("transcript_source_success", ticker=ticker, year=year, quarter=quarter, source="sec_8k")
                return _format_transcript(ticker, year, quarter, "SEC EDGAR 8-K", text)
        except Exception as e:
            logger.warning("sec_8k_transcript_failed", ticker=ticker, year=year, quarter=quarter, error=str(e))

        return None


# 单例
transcript_scraper = TranscriptScraper()
