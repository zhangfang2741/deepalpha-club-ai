"""东财数据中心 / F10 接口（A 股与港股报表、股本、行业、一致预期、研报评级）。只取数，不做口径换算。

数据中心接口：reportName + columns + filter，单页最多 500 行；列名不存在会直接报错（所以按公司类型各配列清单）。
"""

from __future__ import annotations

from datetime import date

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging import logger
from app.services.quant_research.cnhk.http import SourceBusy, get

WEB = "https://datacenter-web.eastmoney.com/api/data/v1/get"
SEC = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
F10_FORECAST = "https://emweb.securities.eastmoney.com/PC_HSF10/ProfitForecast/PageAjax"
REPORT_LIST = "https://reportapi.eastmoney.com/report/list"
PAGE_SIZE = 500
A_SHARE_TYPES = '(SECURITY_TYPE_CODE in ("058001001","058001008"))'  # 沪深京 A 股（不含 B 股、新三板）


async def table(client: httpx.AsyncClient, report: str, columns: str, flt: str | None = None, *,
                base: str = SEC, sort: tuple[str, str] | None = None, max_pages: int = 40,
                extra: dict | None = None) -> list[dict]:
    """拉取一张数据中心表的全部分页；「返回数据为空」给空列表，「服务器繁忙」等重试后仍失败则抛 SourceBusy。"""
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {"reportName": report, "columns": columns, "pageSize": str(PAGE_SIZE), "pageNumber": str(page)}
        if flt:
            params["filter"] = flt
        if sort:
            params["sortColumns"], params["sortTypes"] = sort
        if extra:
            params.update(extra)
        result = await _page(client, base, report, params)
        if result is None:
            return out
        out.extend(result.get("data") or [])
        if page >= int(result.get("pages") or 1):
            return out
    if max_pages > 1:
        logger.warning("eastmoney_table_truncated", report=report, pages=max_pages)
    return out


async def _page(client: httpx.AsyncClient, base: str, report: str, params: dict) -> dict | None:
    async for attempt in AsyncRetrying(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8),
                                       retry=retry_if_exception_type(SourceBusy), reraise=True):
        with attempt:
            resp = await get(client, "eastmoney", base, params)
            try:
                data = resp.json()
            except ValueError as e:
                raise SourceBusy(f"{report}: invalid json") from e
            result = data.get("result") if isinstance(data, dict) else None
            if result:
                return result
            msg = str(data.get("message") or "") if isinstance(data, dict) else ""
            if data.get("code") == 9201 or "数据为空" in msg:
                return None
            raise SourceBusy(f"{report}: {msg or 'empty result'}")
    return None  # pragma: no cover


async def f10_forecast(client: httpx.AsyncClient, code: str) -> dict | None:
    """A 股 F10「盈利预测」整页（pjtj 评级统计 / yctj_list 分年度一致预期 / ycmx 逐家机构预测）。"""
    resp = await get(client, "eastmoney", F10_FORECAST, {"code": a_share_prefixed(code)})
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def research_reports(client: httpx.AsyncClient, code: str, begin: date, end: date,
                           max_pages: int = 6) -> list[dict]:
    """A 股个股研报列表（新 → 旧）：机构、发布日、本次 / 上次评级、目标价、EPS 预测。"""
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        resp = await get(client, "eastmoney", REPORT_LIST, {
            "industryCode": "*", "pageSize": "100", "industry": "*", "rating": "*", "ratingChange": "*",
            "beginTime": begin.isoformat(), "endTime": end.isoformat(), "pageNo": str(page), "fields": "",
            "qType": "0", "orgCode": "", "code": code, "rcode": "",
        })
        data = resp.json() if resp.status_code == 200 else {}
        rows = data.get("data") or []
        out.extend(rows)
        if page >= int(data.get("TotalPage") or 1) or not rows:
            break
    return out


def a_share_prefixed(code: str) -> str:
    """600519 → SH600519（6/9 开头沪市，8/4/920 北交所，其余深市）。"""
    if code.startswith(("6", "9")) and not code.startswith("920"):
        return f"SH{code}"
    if code.startswith(("8", "4", "920")):
        return f"BJ{code}"
    return f"SZ{code}"


def secucode_hk(code: str) -> str:
    """00700 → 00700.HK。"""
    return f"{code}.HK"
