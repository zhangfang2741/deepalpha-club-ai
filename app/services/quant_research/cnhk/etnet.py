"""港股一致预期与券商评级（经济通盈利预测页，一页含逐家券商 EPS / 评级 / 目标价）。

页面里的表按表头关键字定位（外层有嵌套表，下标不稳定）。EPS 单位写在表头括号里：分（人民币）、港仙、美仙……；
表头为空（个别外币申报公司）时由调用方给出申报币种兜底。目标价一律港元。财年按截止年份标注（3 月年结的 2027 = 截至 2027-03）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from io import StringIO

import httpx
import pandas as pd

from app.services.quant_research.cnhk.http import get

URL = "https://www.etnet.com.hk/www/sc/stocks/realtime/quote_profit.php"

# 表头里的单位 → (币种, 换算到元的系数)
UNITS: dict[str, tuple[str, float]] = {
    "分": ("CNY", 0.01), "人民币分": ("CNY", 0.01), "港仙": ("HKD", 0.01), "美仙": ("USD", 0.01),
    "欧仙": ("EUR", 0.01), "仙": ("HKD", 0.01),
    "人民币元": ("CNY", 1.0), "元": ("CNY", 1.0), "港元": ("HKD", 1.0), "美元": ("USD", 1.0), "欧元": ("EUR", 1.0),
}
# 东财报告清单的申报币种 → ISO
CURRENCY_NAMES: dict[str, str] = {"人民币": "CNY", "港元": "HKD", "港币": "HKD", "美元": "USD", "欧元": "EUR",
                                  "英镑": "GBP", "日元": "JPY", "新加坡元": "SGD", "澳元": "AUD", "加元": "CAD"}


@dataclass(frozen=True)
class BrokerRow:
    fiscal_year: int
    eps: float | None          # 已换算成「元」（币种见 EtnetForecast.currency）
    net_income: float | None   # 百万
    firm: str
    rating: str | None         # 只有第一财年的行有
    target_hkd: float | None
    updated: date | None


@dataclass(frozen=True)
class EtnetForecast:
    currency: str | None
    rows: list[BrokerRow]


async def fetch(client: httpx.AsyncClient, code: str) -> str | None:
    """页面 HTML；经济通代码不补零（00700 → 700）。"""
    resp = await get(client, "etnet", URL, {"code": str(int(code))})
    return resp.text if resp.status_code == 200 else None


def _num(v) -> float | None:
    s = str(v).replace(",", "").strip()
    if s in ("", "--", "nan", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _date(v) -> date | None:
    s = str(v).replace("\xa0", " ").strip()
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        return None


def _unit(header: str) -> tuple[str, float] | None:
    m = re.search(r"\(([^()]*)\)\s*$", header.strip())
    return UNITS.get(m.group(1).strip()) if m and m.group(1).strip() else None


def parse(html: str, fallback_currency: str | None = None) -> EtnetForecast | None:
    """解析逐家券商预测表；没有券商覆盖返回 None。fallback_currency 为 ISO 币种（表头没写单位时按「分」级单位）。"""
    try:
        tables = pd.read_html(StringIO(html), header=None)
    except ValueError:
        return None
    broker = next((t for t in tables if t.shape[1] >= 8 and "证券商" in [str(x) for x in t.iloc[0].tolist()]), None)
    if broker is None:
        return None
    header = [str(x) for x in broker.iloc[0].tolist()]
    unit = _unit(header[2]) or ((fallback_currency, 0.01) if fallback_currency else None)
    rows: list[BrokerRow] = []
    for _, r in broker.iloc[1:].iterrows():
        vals = r.tolist()
        fy = _num(vals[0])
        firm = str(vals[4]).strip() if vals[4] is not None else ""
        if fy is None or not firm or firm == "nan":
            continue
        eps = _num(vals[2])
        rating = str(vals[5]).strip() if str(vals[5]).strip() not in ("--", "nan", "") else None
        rows.append(BrokerRow(int(fy), eps * unit[1] if (eps is not None and unit) else None, _num(vals[1]), firm,
                              rating, _num(vals[6]), _date(vals[-1])))
    if not rows:
        return None
    return EtnetForecast(unit[0] if unit else None, rows)
