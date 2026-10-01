"""宏观日历：只保留白名单里的高重要度事件，名字翻成中文 / 英文短名，时间换成市场本地时区。

原始事件时间为 UTC（实测：美联储利率决议 18:00 = 美东 14:00）。
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.schemas.macro import MacroEventOut

# 原始事件名（去掉括号里的期数）→ (重要度, 中文名, 英文名)
US_EVENTS: dict[str, tuple[int, str, str]] = {
    "Fed Interest Rate Decision": (3, "美联储利率决议", "Fed Rate Decision"),
    "Inflation Rate YoY": (3, "CPI 通胀（同比）", "CPI YoY"),
    "Core Inflation Rate YoY": (3, "核心 CPI（同比）", "Core CPI YoY"),
    "Non Farm Payrolls": (3, "非农就业", "Nonfarm Payrolls"),
    "Core PCE Price Index YoY": (2, "核心 PCE（同比）", "Core PCE YoY"),
    "Unemployment Rate": (2, "失业率", "Unemployment Rate"),
    "GDP Growth Rate QoQ": (2, "GDP（环比年化）", "GDP QoQ"),
    "FOMC Minutes": (2, "美联储会议纪要", "FOMC Minutes"),
    "Producer Price Index MoM": (1, "PPI（环比）", "PPI MoM"),
    "Retail Sales MoM": (1, "零售销售（环比）", "Retail Sales MoM"),
    "ISM Manufacturing PMI": (1, "ISM 制造业 PMI", "ISM Manufacturing PMI"),
    "ISM Services PMI": (1, "ISM 服务业 PMI", "ISM Services PMI"),
}

EVENTS_BY_COUNTRY: dict[str, dict[str, tuple[int, str, str]]] = {"US": US_EVENTS}
MARKET_TZ: dict[str, str] = {"us": "America/New_York", "cn": "Asia/Shanghai", "hk": "Asia/Hong_Kong"}
MARKET_COUNTRIES: dict[str, list[str]] = {"us": ["US"]}


def _base_name(event: str) -> str:
    return event.split(" (")[0].strip()


def filter_events(raw: list[dict], market: str, now: datetime, lang: str = "zh",
                  days: int = 7) -> list[MacroEventOut]:
    """raw 为日历原始事件（date 为 UTC 'YYYY-MM-DD HH:MM:SS'）。只留 now 之后 days 天内的白名单事件。"""
    tz = ZoneInfo(MARKET_TZ.get(market, "UTC"))
    countries = set(MARKET_COUNTRIES.get(market, []))
    utc = ZoneInfo("UTC")
    out: list[tuple[datetime, int, MacroEventOut]] = []
    seen: set[tuple[str, str]] = set()
    for e in raw:
        country = str(e.get("country") or "")
        if country not in countries:
            continue
        meta = EVENTS_BY_COUNTRY.get(country, {}).get(_base_name(str(e.get("event") or "")))
        if meta is None:
            continue
        try:
            t = datetime.strptime(str(e.get("date")), "%Y-%m-%d %H:%M:%S").replace(tzinfo=utc)
        except ValueError:
            continue
        delta = (t - now).total_seconds()
        if delta < 0 or delta > days * 86400:
            continue
        importance, zh, en = meta
        local = t.astimezone(tz)
        name = en if lang == "en" else zh
        key = (local.date().isoformat(), name)
        if key in seen:
            continue
        seen.add(key)
        out.append((t, importance, MacroEventOut(date=local.date().isoformat(), time=local.strftime("%H:%M"),
                                                 country=country, name=name, importance=importance)))
    # 同一时刻发布的（如非农与失业率）重要的排前面
    out.sort(key=lambda x: (x[0], -x[1]))
    return [ev for _, _, ev in out]


def next_key_event(events: list[MacroEventOut]) -> MacroEventOut | None:
    """宏观格第二行：最近一个重要度 ≥2 的事件，没有则取最近一个。"""
    for ev in events:
        if ev.importance >= 2:
            return ev
    return events[0] if events else None
