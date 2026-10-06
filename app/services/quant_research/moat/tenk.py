"""SEC 10-K：找最新一份年报、截取 Item 1（业务）正文。

SEC 公平访问要求带 User-Agent、每秒不超过 10 次；这里进程内并发 _CONCURRENCY、每次请求后停 _PAUSE 秒。
「找最新 10-K」只要 1 次请求，每日检查新年报只走这一步；正文只在需要重新评估时才下载。
"""

from __future__ import annotations

import asyncio
import re
import time
import warnings
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from app.core.logging import logger

SEC_HEADERS = {"User-Agent": "DeepAlpha research contact@deepalpha.club", "Accept-Encoding": "gzip, deflate"}
SECTION_CHARS = 45_000
HEAD_CHARS = 30_000
_CONCURRENCY = 4
_PAUSE = 0.15
_TICKER_TTL = 86400
_gate = asyncio.Semaphore(_CONCURRENCY)
_tickers: dict[str, int] = {}
_tickers_at = 0.0

_KEYWORDS = re.compile(r"compet|trademark|patent|brand|licens|switching|network|scale|cost|market share|"
                       r"customer|contract|regulat|barrier|proprietary|intellectual property", re.I)
_SPACES = re.compile(r"[ \t\xa0   ​]+")
_RISK_HEADING = re.compile(r"(?im)^\W*item\W*1a\W*(?:\n\W*)?risk\W*factors\W*$")
_BUSINESS_HEADING = re.compile(r"(?im)^\W*item\W*1(?![0-9a-z])\W*(?:\n\W*)?business\W*$")


@dataclass(frozen=True)
class TenK:
    accession: str
    filed_date: str
    url: str


async def _get(client: httpx.AsyncClient, url: str, timeout: float = 30) -> httpx.Response:
    async with _gate:
        try:
            return await client.get(url, headers=SEC_HEADERS, timeout=timeout)
        finally:
            await asyncio.sleep(_PAUSE)


async def _cik(client: httpx.AsyncClient, symbol: str) -> int | None:
    global _tickers_at
    if not _tickers or time.time() - _tickers_at > _TICKER_TTL:
        r = await _get(client, "https://www.sec.gov/files/company_tickers.json")
        r.raise_for_status()
        _tickers.clear()
        _tickers.update({v["ticker"]: int(v["cik_str"]) for v in r.json().values()})
        _tickers_at = time.time()
    return _tickers.get(symbol.replace(".", "-"))


async def latest_10k(client: httpx.AsyncClient, symbol: str) -> TenK | None:
    """最近一份 10-K 的编号、披露日与正文链接；没有（如外国公司报 20-F）返回 None。"""
    cik = await _cik(client, symbol)
    if cik is None:
        return None
    r = await _get(client, f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    r.raise_for_status()
    recent = r.json()["filings"]["recent"]
    idx = next((i for i, f in enumerate(recent["form"]) if f == "10-K"), None)
    if idx is None:
        return None
    acc = recent["accessionNumber"][idx]
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{recent['primaryDocument'][idx]}"
    return TenK(acc, recent["filingDate"][idx], url)


@dataclass(frozen=True)
class Periodic:
    form: str
    filed_date: str
    period: str | None
    url: str


_PERIODIC_FORMS = ("10-K", "10-Q", "20-F", "40-F")


async def latest_periodic(client: httpx.AsyncClient, symbol: str) -> Periodic | None:
    """最近一份定期报告（10-K / 10-Q，外国公司 20-F / 40-F）：表单、披露日、报告期末、正文链接。"""
    cik = await _cik(client, symbol)
    if cik is None:
        return None
    r = await _get(client, f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    r.raise_for_status()
    recent = r.json()["filings"]["recent"]  # 新 → 旧
    idx = next((i for i, f in enumerate(recent["form"]) if f in _PERIODIC_FORMS), None)
    if idx is None:
        return None
    acc = recent["accessionNumber"][idx].replace("-", "")
    doc = recent["primaryDocument"][idx]
    # primaryDocument 常带 xsl 渲染前缀（如 xslF345X05/…），去掉才是原始文档；这里的文档名是纯文件名
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
    period = (recent.get("reportDate") or [None] * (idx + 1))[idx] or None
    return Periodic(recent["form"][idx], recent["filingDate"][idx], period, url)


async def business_section(client: httpx.AsyncClient, tenk: TenK) -> str | None:
    """下载 10-K 正文并截取 Item 1。"""
    r = await _get(client, tenk.url, timeout=90)
    r.raise_for_status()
    section = extract_business(r.text)
    if section is None:
        logger.warning("quant_moat_section_missing", url=tenk.url)
    return section


def extract_business(html: str) -> str | None:
    """取行首「ITEM 1 业务」标题到「ITEM 1A 风险因素」标题之间的正文。

    每个「1A」标题与上一个之间只取第一个「1 业务」标题：避开目录里的同名条目，
    也避开每页页眉重复印的「ITEM 1. BUSINESS」（MA 年报曾因此只截到最后一页的监管条文）。
    超长时保留开头 + 竞争 / 商标 / 专利等关键词段落；找不到标准标题时退回关键词段落。
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = BeautifulSoup(html, "lxml").get_text("\n")
    text = re.sub(r"\n\s*\n+", "\n", _SPACES.sub(" ", raw))
    best, prev = "", 0
    for m in _RISK_HEADING.finditer(text):
        first = _BUSINESS_HEADING.search(text[prev:m.start()])
        if first and m.start() - (prev + first.start()) > len(best):
            best = text[prev + first.start():m.start()]
        prev = m.start()
    if len(best) < 2000:
        return _keyword_fallback(text)
    if len(best) <= SECTION_CHARS:
        return best
    tail = "\n".join(p for p in best[HEAD_CHARS:].split("\n") if _KEYWORDS.search(p))
    return best[:HEAD_CHARS] + "\n…\n" + tail[: SECTION_CHARS - HEAD_CHARS]


def _keyword_fallback(text: str) -> str | None:
    """非标准 10-K（只有页眉、条目对照表放在文末等）：取前 60% 正文里讲竞争 / 品牌 / 专利 / 客户的长段落。"""
    body = text[: int(len(text) * 0.6)]
    joined = "\n".join(p for p in body.split("\n") if len(p) >= 200 and _KEYWORDS.search(p))[:SECTION_CHARS]
    return joined if len(joined) > 2000 else None
