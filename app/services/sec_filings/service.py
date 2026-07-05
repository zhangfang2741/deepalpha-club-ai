"""SEC EDGAR filing 列表与分类服务。

数据源（均为 SEC 官方免费接口，需带 User-Agent）：
1. www.sec.gov/files/company_tickers.json —— 全量 ticker → CIK 映射
2. data.sec.gov/submissions/CIK{10位}.json —— 单公司全部 filing（近 1000 条）
3. data.sec.gov/submissions/{溢出文件名} —— 更早年份的 filing

正确性优先：按公司一次性拉全部 filing，本地按 form type 分类；
每条同时保留「提交日 filingDate」和「报告期 reportDate」——二者可能不同。
"""

import asyncio
import json
import re
from typing import Optional

import httpx
from redis.asyncio import Redis
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.logging import logger
from app.services.sec_filings.constants import (
    CATEGORIES,
    classify_form,
    describe_8k_items,
    describe_exhibit,
    describe_form,
)

_HEADERS = {
    "User-Agent": "DeepAlpha/1.0 (investment research; mailto:research@deepalpha.ai)",
    "Accept-Encoding": "gzip, deflate",
}

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

# 缓存 key 与 TTL
_TICKERS_CACHE_KEY = "sec:tickers_map"
_TICKERS_TTL = 86400  # 24h：映射表变动极慢
_SUBMISSIONS_CACHE_PREFIX = "sec:submissions"
_SUBMISSIONS_TTL = 3600  # 1h
_DOCS_CACHE_PREFIX = "sec:docs"
_DOCS_TTL = 86400  # 24h：单份 filing 的文档清单不变

# 拉取历史溢出文件的上限，避免超大公司拖垮响应（每文件约 1000 条）
_MAX_OVERFLOW_FILES = 4


def _normalize_cik(cik_raw: str | int) -> str:
    """CIK 规范化为 10 位补零字符串。"""
    return str(cik_raw).strip().lstrip("0").zfill(10)


class SecFilingsService:
    """SEC filing 列表 + 分类。"""

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        # 进程内 ticker 映射缓存（避免每次都反序列化 800KB JSON）
        self._ticker_map: Optional[dict[str, dict]] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30, headers=_HEADERS)
        return self._client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _get_json(self, url: str) -> dict | list:
        client = await self._get_client()
        resp = await client.get(url)
        resp.raise_for_status()
        # SEC 限速 10 req/s，礼貌间隔
        await asyncio.sleep(0.12)
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _get_text(self, url: str) -> str:
        client = await self._get_client()
        resp = await client.get(url)
        resp.raise_for_status()
        await asyncio.sleep(0.12)
        return resp.text

    # ---------- ticker -> CIK ----------

    async def _load_ticker_map(self, redis: Optional[Redis]) -> dict[str, dict]:
        """加载 ticker -> {cik, name} 映射，多级缓存：进程内 -> Redis -> SEC。"""
        if self._ticker_map is not None:
            return self._ticker_map

        # Redis 缓存
        if redis is not None:
            try:
                raw = await redis.get(_TICKERS_CACHE_KEY)
                if raw:
                    self._ticker_map = json.loads(raw)
                    return self._ticker_map
            except Exception as e:
                logger.warning("sec_tickers_cache_read_error", error=str(e))

        # 回源 SEC
        data = await self._get_json(_TICKERS_URL)
        mapping: dict[str, dict] = {}
        # 结构：{"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        for entry in data.values():
            ticker = str(entry.get("ticker", "")).upper()
            if not ticker:
                continue
            mapping[ticker] = {
                "cik": _normalize_cik(entry.get("cik_str", "")),
                "name": entry.get("title", ""),
            }
        self._ticker_map = mapping

        if redis is not None:
            try:
                await redis.set(
                    _TICKERS_CACHE_KEY,
                    json.dumps(mapping, ensure_ascii=False),
                    ex=_TICKERS_TTL,
                )
            except Exception as e:
                logger.warning("sec_tickers_cache_write_error", error=str(e))

        logger.info("sec_tickers_map_loaded", count=len(mapping))
        return mapping

    async def resolve_cik(
        self, query: str, redis: Optional[Redis] = None
    ) -> Optional[dict]:
        """将 ticker 或 CIK 解析为 {cik, name, ticker}。找不到返回 None。"""
        q = query.strip().upper()
        if not q:
            return None

        mapping = await self._load_ticker_map(redis)

        # 直接是 ticker
        if q in mapping:
            return {"ticker": q, **mapping[q]}

        # 纯数字：当作 CIK 处理，反查 name/ticker
        digits = q.lstrip("0")
        if digits.isdigit():
            cik = _normalize_cik(q)
            for tk, v in mapping.items():
                if v["cik"] == cik:
                    return {"ticker": tk, "cik": cik, "name": v["name"]}
            # 映射表里没有（可能是非上市实体），仍返回 CIK
            return {"ticker": "", "cik": cik, "name": ""}

        return None

    # ---------- submissions ----------

    async def _fetch_all_filings(self, cik: str) -> tuple[dict, list[dict]]:
        """拉取一家公司全部 filing（近期 + 溢出历史）。

        Returns:
            (公司元信息 dict, 扁平化 filing 列表)
        """
        url = f"{_SUBMISSIONS_BASE}/CIK{cik}.json"
        meta = await self._get_json(url)

        company = {
            "cik": cik,
            "name": meta.get("name", ""),
            "tickers": meta.get("tickers", []),
            "exchanges": meta.get("exchanges", []),
            "sic_description": meta.get("sicDescription", ""),
        }

        recent = meta.get("filings", {}).get("recent", {})
        filings = self._parse_filing_arrays(recent, cik)

        # 溢出历史文件
        overflow = meta.get("filings", {}).get("files", []) or []
        for f in overflow[:_MAX_OVERFLOW_FILES]:
            name = f.get("name")
            if not name:
                continue
            try:
                arr = await self._get_json(f"{_SUBMISSIONS_BASE}/{name}")
                filings.extend(self._parse_filing_arrays(arr, cik))
            except Exception as e:
                logger.warning("sec_overflow_fetch_error", name=name, error=str(e))

        return company, filings

    def _parse_filing_arrays(self, arr: dict, cik: str) -> list[dict]:
        """将 SEC 的列向量结构转成 filing 记录列表。"""
        forms = arr.get("form", [])
        accs = arr.get("accessionNumber", [])
        filing_dates = arr.get("filingDate", [])
        report_dates = arr.get("reportDate", [])
        primary_docs = arr.get("primaryDocument", [])
        primary_descs = arr.get("primaryDocDescription", [])
        items = arr.get("items", [])
        cik_int = cik.lstrip("0") or "0"

        records: list[dict] = []
        for i, form in enumerate(forms):
            acc = accs[i] if i < len(accs) else ""
            acc_nodash = acc.replace("-", "")
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""
            item_raw = items[i] if i < len(items) else ""

            index_url = (
                f"{_ARCHIVES_BASE}/{cik_int}/{acc_nodash}/{acc}-index.htm"
                if acc
                else ""
            )
            doc_url = (
                f"{_ARCHIVES_BASE}/{cik_int}/{acc_nodash}/{primary_doc}"
                if primary_doc
                else ""
            )

            form_info = describe_form(form)
            records.append({
                "form": form,
                "form_name": form_info["name"],
                "form_desc": form_info["desc"],
                "category": classify_form(form),
                "filing_date": filing_dates[i] if i < len(filing_dates) else "",
                "report_date": report_dates[i] if i < len(report_dates) else "",
                "accession_number": acc,
                "primary_doc_description": primary_descs[i] if i < len(primary_descs) else "",
                "items": describe_8k_items(item_raw) if form.upper().startswith("8-K") else [],
                "index_url": index_url,
                "doc_url": doc_url,
            })
        return records

    # ---------- 单份 filing 的文档/附件清单 ----------

    async def get_filing_documents(
        self, cik: str, accession: str, redis: Optional[Redis] = None
    ) -> Optional[dict]:
        """解析一份 filing 的文档表格，返回其全部附件（含类型/中文标签/链接）。

        对 8-K Item 2.02，会把业绩新闻稿（EX-99.1）等标为 highlight。

        Returns:
            {accession, documents:[{seq, type, label, description, filename, url, highlight}]}
        """
        cik_norm = _normalize_cik(cik)
        acc = accession.strip()
        acc_nodash = acc.replace("-", "")
        cik_int = cik_norm.lstrip("0") or "0"

        cache_key = f"{_DOCS_CACHE_PREFIX}:{cik_int}:{acc_nodash}"
        if redis is not None:
            try:
                raw = await redis.get(cache_key)
                if raw:
                    return json.loads(raw)
            except Exception as e:
                logger.warning("sec_docs_cache_read_error", error=str(e))

        base = f"{_ARCHIVES_BASE}/{cik_int}/{acc_nodash}"
        index_url = f"{base}/{acc}-index.htm"
        try:
            html = await self._get_text(index_url)
        except Exception as e:
            logger.warning("sec_filing_index_fetch_error", acc=acc, error=str(e))
            return None

        documents = self._parse_document_table(html, base)
        result = {"accession": acc, "index_url": index_url, "documents": documents}

        if redis is not None:
            try:
                await redis.set(cache_key, json.dumps(result, ensure_ascii=False), ex=_DOCS_TTL)
            except Exception as e:
                logger.warning("sec_docs_cache_write_error", error=str(e))

        logger.info("sec_filing_documents_loaded", acc=acc, count=len(documents))
        return result

    @staticmethod
    def _parse_document_table(html: str, base_url: str) -> list[dict]:
        """解析 EDGAR filing index 页的「Document Format Files」表格。

        表列结构：[序号, 描述, 文档(可能带 iXBRL 标记), 类型, 大小]。
        隐藏 XBRL/图片等无阅读价值的附件；EX-99.x 标 highlight。
        """
        docs: list[dict] = []
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I)
        for row in rows:
            cells_raw = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)
            if len(cells_raw) < 5:
                continue

            def _clean(x: str) -> str:
                x = re.sub(r"<[^>]+>", " ", x)
                x = x.replace("&nbsp;", " ").replace("&amp;", "&")
                return re.sub(r"\s+", " ", x).strip()

            seq = _clean(cells_raw[0])
            description = _clean(cells_raw[1])
            doc_cell = _clean(cells_raw[2])
            ex_type = _clean(cells_raw[3])

            # 文档名：去掉「 iXBRL」等尾注，取第一段
            filename = doc_cell.split(" ")[0] if doc_cell else ""
            if not filename or not filename.lower().endswith((".htm", ".html", ".txt", ".pdf")):
                continue

            # 主文件：序号为 1 且类型是表格本身（非 EX-*）
            is_primary = seq == "1" and not ex_type.upper().startswith("EX-")
            info = describe_exhibit(ex_type, description, is_primary)
            if info["skip"]:
                continue

            docs.append({
                "seq": seq,
                "type": ex_type,
                "label": info["label"],
                "description": description if description.upper() != ex_type.upper() else "",
                "filename": filename,
                "url": f"{base_url}/{filename}",
                "highlight": info["highlight"],
            })
        return docs

    # ---------- 对外主入口 ----------

    async def get_company_filings(
        self, query: str, redis: Optional[Redis] = None
    ) -> Optional[dict]:
        """按 ticker/CIK 获取公司全部 filing，并按分类分组。

        Returns:
            {company, categories: [{key, label, count, filings:[...]}], total} 或 None
        """
        resolved = await self.resolve_cik(query, redis)
        if not resolved:
            return None
        cik = resolved["cik"]

        # Redis 缓存整份结果
        cache_key = f"{_SUBMISSIONS_CACHE_PREFIX}:{cik}"
        if redis is not None:
            try:
                raw = await redis.get(cache_key)
                if raw:
                    return json.loads(raw)
            except Exception as e:
                logger.warning("sec_submissions_cache_read_error", error=str(e))

        try:
            company, filings = await self._fetch_all_filings(cik)
        except Exception as e:
            logger.exception("sec_filings_fetch_failed", cik=cik, error=str(e))
            return None

        # ticker 映射里拿到的公司名兜底
        if not company.get("name") and resolved.get("name"):
            company["name"] = resolved["name"]

        # 按分类分组（保持 filing 的时间倒序——SEC 返回本就是新→旧）
        grouped: dict[str, list] = {k: [] for k in CATEGORIES}
        for rec in filings:
            grouped[rec["category"]].append(rec)

        categories = []
        for key, meta in sorted(CATEGORIES.items(), key=lambda kv: kv[1]["order"]):
            categories.append({
                "key": key,
                "label": meta["label"],
                "label_en": meta["label_en"],
                "count": len(grouped[key]),
                "filings": grouped[key],
            })

        result = {
            "company": company,
            "total": len(filings),
            "categories": categories,
        }

        if redis is not None:
            try:
                await redis.set(
                    cache_key,
                    json.dumps(result, ensure_ascii=False),
                    ex=_SUBMISSIONS_TTL,
                )
            except Exception as e:
                logger.warning("sec_submissions_cache_write_error", error=str(e))

        logger.info(
            "sec_company_filings_loaded",
            cik=cik,
            name=company.get("name"),
            total=len(filings),
        )
        return result

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# 单例
sec_filings_service = SecFilingsService()
