"""SEC EDGAR 文档获取服务。

提供两种数据路径：
1. 全文搜索 API（efts.sec.gov）→ 按关键词或股票代码查找文件
2. 归档直链抓取（www.sec.gov/Archives）→ 获取文件正文纯文本
"""

import asyncio
import re
from html.parser import HTMLParser
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.logging import logger

_HEADERS = {
    "User-Agent": "DeepAlpha/1.0 (investment research; mailto:research@deepalpha.ai)",
    "Accept-Encoding": "gzip, deflate",
}

_SEARCH_BASE = "https://efts.sec.gov/LATEST/search-index"
_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
# SEC 官方 ticker → CIK 全量映射文件（覆盖全部美股上市公司）
_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

# 内置 CIK 种子表（NVIDIA 生态核心公司），作为离线兜底 + 常用代码快速命中。
# 完整解析改由 SEC company_tickers.json 动态加载，任意美股代码均可解析。
_TICKER_CIK: dict[str, str] = {
    "NVDA": "0001045810",
    "TSMC": "0001046179",
    "MU": "0000723125",
    "MSFT": "0000789019",
    "META": "0001326801",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "AVGO": "0001054374",
    "AMD": "0000002488",
    "INTC": "0000050863",
    "AMAT": "0000796343",
    "LRCX": "0000707549",
    "VRT": "0001688568",
    "SMCI": "0001375365",
    "DELL": "0000826083",
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
            self._current_skip -= 1

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
    # 合并连续空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_cik(cik_raw: str) -> str:
    """将 CIK 规范化为 10 位补零字符串。"""
    return cik_raw.strip().lstrip("0").zfill(10)


class SecEdgarFetcher:
    """SEC EDGAR 文档抓取客户端。"""

    def __init__(self):  # noqa: D107
        self._client: Optional[httpx.AsyncClient] = None
        # 动态 CIK 缓存：ticker(大写) → 10 位补零 CIK。启动时预置内置种子表，
        # 首次遇到未命中的代码时懒加载 SEC 全量映射补齐。
        self._cik_cache: dict[str, str] = dict(_TICKER_CIK)
        self._full_map_loaded = False
        self._map_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60, headers=_HEADERS)
        return self._client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, url: str, params: Optional[dict] = None) -> httpx.Response:
        client = await self._get_client()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        # SEC 限速：10 req/s
        await asyncio.sleep(0.12)
        return resp

    async def _load_full_ticker_map(self) -> None:
        """懒加载 SEC 官方 company_tickers.json，补齐 ticker→CIK 全量映射（仅一次）。"""
        if self._full_map_loaded:
            return
        async with self._map_lock:
            if self._full_map_loaded:
                return
            try:
                resp = await self._get(_TICKER_MAP_URL)
                data = resp.json()
                # 数据形如 {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
                loaded = 0
                for item in data.values():
                    tk = str(item.get("ticker", "")).upper()
                    cik_raw = item.get("cik_str")
                    if tk and cik_raw is not None:
                        # setdefault：不覆盖内置种子（种子里的别名/自定义映射优先）
                        self._cik_cache.setdefault(tk, str(cik_raw).zfill(10))
                        loaded += 1
                self._full_map_loaded = True
                logger.info("sec_ticker_map_loaded", count=loaded)
            except Exception as e:
                # 加载失败不致命：仍可依赖内置种子表，下次未命中再重试
                logger.warning("sec_ticker_map_load_failed", error=str(e))

    async def _resolve_cik(self, ticker: str) -> Optional[str]:
        """解析 ticker 对应的 CIK：先查缓存（含内置种子），未命中则加载 SEC 全量映射。"""
        key = ticker.upper()
        cik = self._cik_cache.get(key)
        if cik:
            return cik
        await self._load_full_ticker_map()
        return self._cik_cache.get(key)

    async def search_filings(
        self,
        ticker: str,
        form_types: list[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 10,
    ) -> list[dict]:
        """用 EDGAR 全文搜索接口检索文件列表。

        Args:
            ticker: 股票代码（如 NVDA）
            form_types: 文件类型列表（如 ["10-K", "10-Q"]）
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            max_results: 最多返回条数

        Returns:
            文件元信息列表，每条含 url / filing_date / period / form
        """
        params: dict = {
            "q": f'"{ticker.upper()}"',
            "forms": ",".join(form_types),
            "hits.hits._source": (
                "period_of_report,file_date,entity_name,file_num,"
                "form_type,biz_location,inc_states"
            ),
            "hits.hits.total.value": "true",
            "_source": "true",
        }
        if start_date:
            params["dateRange"] = "custom"
            params["startdt"] = start_date
        if end_date:
            params["enddt"] = end_date

        try:
            resp = await self._get(_SEARCH_BASE, params)
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])

            results = []
            for hit in hits[:max_results]:
                src = hit.get("_source", {})
                entity_id = hit.get("_id", "")

                # 构建文档 URL
                # _id 格式：{cik}:{accession_dashed}
                doc_url = None
                if ":" in entity_id:
                    parts = entity_id.split(":")
                    if len(parts) >= 2:
                        cik_raw = parts[0]
                        acc = parts[1].replace("-", "")
                        cik_num = cik_raw.lstrip("0") or "0"
                        doc_url = f"{_ARCHIVES_BASE}/{cik_num}/{acc}/"

                results.append({
                    "form": src.get("form_type", ""),
                    "filing_date": src.get("file_date", ""),
                    "period_of_report": src.get("period_of_report", ""),
                    "entity_name": src.get("entity_name", ticker),
                    "ticker": ticker.upper(),
                    "index_url": doc_url,
                    "entity_id": entity_id,
                })

            logger.info(
                "sec_search_completed",
                ticker=ticker,
                forms=form_types,
                result_count=len(results),
            )
            return results

        except Exception as e:
            logger.exception("sec_search_failed", ticker=ticker, error=str(e))
            return []

    async def get_filing_index(self, cik: str, accession_no: str) -> list[dict]:
        """获取文件目录（index），返回文件清单。

        Args:
            cik: 公司 CIK（数字，无需补零）
            accession_no: 格式 0001045810-24-000001（含连字符）

        Returns:
            文件清单列表，含 filename / description / type
        """
        acc_no_dashes = accession_no.replace("-", "")
        url = f"{_ARCHIVES_BASE}/{cik}/{acc_no_dashes}/{accession_no}-index.json"
        try:
            resp = await self._get(url)
            data = resp.json()
            return data.get("directory", {}).get("item", [])
        except Exception as e:
            logger.warning("sec_index_fetch_failed", cik=cik, acc=accession_no, error=str(e))
            return []

    async def fetch_document_text(self, doc_url: str) -> str:
        """从 SEC 归档抓取文件正文，自动处理 HTML/文本两种格式。

        Args:
            doc_url: 文件直链（如 .htm / .txt / .xml）

        Returns:
            清洗后的纯文本内容
        """
        try:
            resp = await self._get(doc_url)
            content_type = resp.headers.get("content-type", "")
            raw = resp.text

            if "html" in content_type or doc_url.lower().endswith((".htm", ".html")):
                text = _html_to_text(raw)
            else:
                # 纯文本：去除 SGML/XBRL 标签头
                text = re.sub(r"<[^>]+>", " ", raw)
                text = re.sub(r"\s{3,}", "\n\n", text).strip()

            logger.info("sec_document_fetched", url=doc_url[:80], text_len=len(text))
            return text

        except Exception as e:
            logger.exception("sec_document_fetch_failed", url=doc_url, error=str(e))
            return ""

    async def get_submissions_meta(self, ticker: str) -> Optional[dict]:
        """通过 submissions API 查找公司最新文件列表（补充 search 的精确度）。"""
        cik = await self._resolve_cik(ticker)
        if not cik:
            logger.warning("cik_not_found", ticker=ticker)
            return None
        url = f"{_SUBMISSIONS_BASE}/CIK{cik}.json"
        try:
            resp = await self._get(url)
            return resp.json()
        except Exception as e:
            logger.exception("sec_submissions_failed", ticker=ticker, error=str(e))
            return None

    async def fetch_latest_filing_text(
        self,
        ticker: str,
        form_type: str = "10-K",
        section_hint: Optional[str] = None,
    ) -> tuple[str, dict]:
        """获取最新一份指定类型文件的正文文本。

        Returns:
            (正文文本, 文件元信息字典)
        """
        meta = await self.get_submissions_meta(ticker)
        if not meta:
            return "", {}

        recent = meta.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accs = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])
        periods = recent.get("periodOfReport", [])
        primary_docs = recent.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form == form_type and i < len(accs):
                cik_raw = str(meta.get("cik", "")).lstrip("0")
                acc = accs[i]
                acc_no_dashes = acc.replace("-", "")
                primary_doc = primary_docs[i] if i < len(primary_docs) else ""

                filing_info = {
                    "form": form_type,
                    "ticker": ticker.upper(),
                    "entity_name": meta.get("name", ticker),
                    "filing_date": dates[i] if i < len(dates) else "",
                    "period_of_report": periods[i] if i < len(periods) else "",
                    "doc_url": f"{_ARCHIVES_BASE}/{cik_raw}/{acc_no_dashes}/{primary_doc}",
                    "index_url": f"{_ARCHIVES_BASE}/{cik_raw}/{acc_no_dashes}/",
                }

                if not primary_doc:
                    return "", filing_info

                text = await self.fetch_document_text(filing_info["doc_url"])
                return text, filing_info

        return "", {}

    async def close(self):  # noqa: D102
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# 单例
sec_fetcher = SecEdgarFetcher()
