"""最新定期财报（年报 / 中报 / 季报）原文：美股取 SEC 披露的网页文档，A 股 / 港股取东财公告里的 PDF。

只给链接和元信息，文件由 App 自己下载、缓存在本机；这里不抓取、不转存财报内容。结果 Redis 缓存 12 小时。
"""

from __future__ import annotations

import httpx
from redis.asyncio import Redis

from app.cache.operations import get_json, set_json
from app.core.logging import logger
from app.schemas.quant_research import LatestReportOut
from app.services.quant_research.cnhk.http import get as site_get
from app.services.quant_research.cnhk.http import new_client
from app.services.quant_research.markets import normalize_symbol
from app.services.quant_research.moat import tenk

CACHE_TTL = 12 * 3600
ANN_API = "https://np-anotice-stock.eastmoney.com/api/security/ann"
PDF_URL = "https://pdf.dfcfw.com/pdf/H2_{code}_1.pdf"

# 公告栏目名（东财分类）→ (中文类型, 英文类型)。A 股只收全文；港股年報 / 中期報告 / 季度與中期業績公告都算
_CN_COLUMNS = {"年度报告全文": ("年报", "Annual report"), "半年度报告全文": ("中报", "Interim report"),
               "一季度报告全文": ("季报", "Q1 report"), "三季度报告全文": ("季报", "Q3 report")}
_HK_COLUMNS = {"年報": ("年报", "Annual report"), "中期/半年度報告": ("中报", "Interim report"),
               "季度業績": ("季度业绩公告", "Quarterly results"), "中期業績": ("中期业绩公告", "Interim results"),
               "全年業績": ("全年业绩公告", "Annual results"), "末期業績": ("全年业绩公告", "Annual results")}
# 只要年报：A 股「年度报告全文」、港股「年報」、美股 10-K / 20-F / 40-F
_CN_ANNUAL = {k: v for k, v in _CN_COLUMNS.items() if k == "年度报告全文"}
_HK_ANNUAL = {k: v for k, v in _HK_COLUMNS.items() if k == "年報"}
_US_ANNUAL_FORMS = ("10-K", "20-F", "40-F")
_US_LABELS = {"10-K": ("年报", "Annual report"), "10-Q": ("季报", "Quarterly report"),
              "20-F": ("年报", "Annual report"), "40-F": ("年报", "Annual report")}


def _label(pair: tuple[str, str], lang: str) -> str:
    return pair[0] if lang == "zh" else pair[1]


def cache_key(market: str, symbol: str, lang: str, kind: str = "latest") -> str:
    """缓存键（带版本号，结构变动时升版本）。"""
    return f"quant_research:report:v2:{kind}:{market}:{symbol}:{lang}"


def pick_announcement(rows: list[dict], columns: dict, lang: str, symbol: str) -> LatestReportOut | None:
    """从公告列表（新 → 旧）挑最新一份定期报告。"""
    for a in rows:
        names = [c.get("column_name") for c in a.get("columns") or []]
        hit = next((columns[n] for n in names if n in columns), None)
        code = str(a.get("art_code") or "")
        if hit is None or not code.isalnum():
            continue
        date = str(a.get("notice_date") or a.get("display_time") or "")[:10]
        return LatestReportOut(status="ok", symbol=symbol, title=str(a.get("title") or "") or None,
                               report_type=_label(hit, lang), filed_date=date or None,
                               url=PDF_URL.format(code=code), file_type="pdf")
    return None


async def _latest_announced(client: httpx.AsyncClient, code: str, ann_type: str, columns: dict, lang: str,
                            symbol: str, pages: int = 3) -> LatestReportOut | None:
    """按页取公告（新 → 旧），某一页里一找到定期报告就停，不把后面几页也拉完。"""
    for page in range(1, pages + 1):
        resp = await site_get(client, "eastmoney", ANN_API, {
            "sr": "-1", "page_size": "100", "page_index": str(page), "ann_type": ann_type,
            "client_source": "web", "stock_list": code, "f_node": "0", "s_node": "0"})
        data = resp.json() if resp.status_code == 200 else {}
        rows = (data.get("data") or {}).get("list") or []
        hit = pick_announcement(rows, columns, lang, symbol)
        if hit is not None or len(rows) < 100:
            return hit
    return None


async def get_latest_report(market: str, symbol: str, lang: str, *, redis: Redis | None,
                            kind: str = "latest") -> LatestReportOut:
    """缓存 → 按市场取最新定期报告（kind=annual 只取年报）；取不到给 unavailable（不缓存）。"""
    annual = kind == "annual"
    if market not in ("us", "cn", "hk"):
        return LatestReportOut(status="unsupported_market", symbol=symbol.upper())
    symbol = normalize_symbol(market, symbol)
    key = cache_key(market, symbol, lang, kind)
    if redis is not None:
        try:
            cached = await get_json(redis, key)
            if cached:
                return LatestReportOut(**cached)
        except Exception as e:  # noqa: BLE001
            logger.warning("latest_report_cache_read_failed", symbol=symbol, error=str(e))

    out: LatestReportOut | None = None
    try:
        if market == "us":
            async with httpx.AsyncClient() as client:
                p = await tenk.latest_periodic(client, symbol, _US_ANNUAL_FORMS) if annual else await tenk.latest_periodic(client, symbol)
            if p is not None:
                label = _label(_US_LABELS[p.form], lang)
                out = LatestReportOut(status="ok", symbol=symbol, title=f"{symbol} {p.form}", report_type=label,
                                      period=p.period, filed_date=p.filed_date, url=p.url, file_type="html")
        else:
            async with new_client() as client:
                # 年报一年才一份，可能被后面的季报 / 中报埋得比较深：多翻几页
                pages = 6 if annual else 3
                if market == "cn":
                    out = await _latest_announced(client, symbol, "A", _CN_ANNUAL if annual else _CN_COLUMNS, lang, symbol, pages)
                else:
                    out = await _latest_announced(client, symbol, "H", _HK_ANNUAL if annual else _HK_COLUMNS, lang, symbol, pages)
    except Exception as e:  # noqa: BLE001
        logger.warning("latest_report_failed", market=market, symbol=symbol, error=str(e))
    if out is None:
        return LatestReportOut(status="unavailable", symbol=symbol)
    if redis is not None:
        try:
            await set_json(redis, key, out.model_dump(mode="json"), expire=CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("latest_report_cache_write_failed", key=key, error=str(e))
    return out
