"""A 股 / 港股评级雷达的数据：券商评级上调 / 下调动作。

整理成与美股 `analyst_events` 相同的动作格式，交给同一个 `analyst_radar.build_analyst_radar`
（同一套规则：维持、首次覆盖不算，按净家数放圈）。

- A 股：东财研报列表自带「本次评级 / 上次评级」（同一家券商对同一只股票的前后两次，东财统一后的五档）。
  不带股票代码可以按日期一次拉全市场（近 35 天约 30 页、几秒），档位不同才算一次上调 / 下调。结果缓存 6 小时。
  A 股券商很少改评级（2026-10 实测全市场近 90 天只有约 20 次，多为维持或首次覆盖），所以雷达常常很空——这是市场特点，不是取数问题。
- 港股：经济通只有各券商**当前**评级（没有前评级），所以每天给雷达各港股指数的成分股抓一次，与上一份比对，档位变了记一次，
  日期取券商的更新日期（缺失或早于上次快照就用当天）。从开始抓取那天起累计（`tracking_since`），之前没有数据。
  状态与事件存 Redis（都带 TTL，每天续期）；Redis 被清空只会让累计从头开始，不影响其它功能。
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import httpx
from redis.asyncio import Redis

from app.core.logging import logger
from app.services.quant_research.cnhk.ratings import tier
from app.services.quant_research.markets import normalize_symbol

MARKETS = ("cn", "hk")
CN_LOOKBACK_DAYS = 35            # 评级雷达最外圈 30 天，多留几天余量
CN_MAX_PAGES = 60                # 每页 100 篇；近 35 天实测约 30 页
CN_CACHE_TTL = 6 * 3600
EVENT_KEEP_DAYS = 90
HK_STATE_TTL = 60 * 86400
HK_EVENTS_TTL = 120 * 86400

_PREFIX = "signal_radar:analyst_cnhk:v1"
CN_KEY = f"{_PREFIX}:cn:actions"
HK_STATE_KEY = f"{_PREFIX}:hk:state"
HK_EVENTS_KEY = f"{_PREFIX}:hk:events"
HK_DAY_KEY = f"{_PREFIX}:hk:snapshot_day"
HK_SINCE_KEY = f"{_PREFIX}:hk:since"


def _action(prev: str | None, new: str | None) -> str | None:
    """前后评级 → upgrade / downgrade；任一档位未知、或同档（含同档换说法）返回 None。"""
    tp, tn = tier(prev), tier(new)
    if tp is None or tn is None or tp == tn:
        return None
    return "upgrade" if tn < tp else "downgrade"     # 档位下标越小越看好


def _sorted(out: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {k: sorted(v, key=lambda a: (a["date"], a["firm"]), reverse=True) for k, v in out.items()}


def cn_actions_from_reports(rows: list[dict]) -> dict[str, list[dict]]:
    """东财研报行 → {6 位代码: 上调 / 下调动作（新到旧）}。"""
    out: dict[str, list[dict]] = {}
    for r in rows:
        prev, new = r.get("lastEmRatingName"), r.get("emRatingName")
        action = _action(prev, new)
        code = str(r.get("stockCode") or "").strip()
        day = str(r.get("publishDate") or "")[:10]
        if action is None or not code or len(day) != 10:
            continue
        out.setdefault(normalize_symbol("cn", code), []).append(
            {"date": day, "firm": str(r.get("orgSName") or "").strip(), "prev": str(prev).strip(),
             "new": str(new).strip(), "action": action})
    return _sorted(out)


async def _fetch_cn_reports(client: httpx.AsyncClient, begin: date, end: date) -> list[dict]:
    """全市场 A 股个股研报（不带代码），按页拉完。"""
    from app.services.quant_research.cnhk.eastmoney import REPORT_LIST
    from app.services.quant_research.cnhk.http import get

    rows: list[dict] = []
    for page in range(1, CN_MAX_PAGES + 1):
        resp = await get(client, "eastmoney", REPORT_LIST, {
            "industryCode": "*", "pageSize": "100", "industry": "*", "rating": "*", "ratingChange": "*",
            "beginTime": begin.isoformat(), "endTime": end.isoformat(), "pageNo": str(page), "fields": "",
            "qType": "0", "orgCode": "", "code": "", "rcode": "",
        })
        data = resp.json() if resp.status_code == 200 else {}
        batch = data.get("data") or []
        rows.extend(batch)
        if not batch or page >= int(data.get("TotalPage") or 1):
            break
    return rows


async def cn_actions(redis: Redis | None, as_of: date, *, refresh: bool = False) -> dict[str, list[dict]]:
    """A 股全市场近 35 天的评级上调 / 下调（缓存 6 小时；refresh 强制重拉）。取数失败返回缓存或空。"""
    if redis is not None and not refresh:
        try:
            if raw := await redis.get(CN_KEY):
                return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            logger.warning("signal_radar_cn_analyst_cache_read_failed", error=str(e))
    from app.services.quant_research.cnhk.http import _UA

    try:
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": _UA}, trust_env=False) as client:
            rows = await _fetch_cn_reports(client, as_of - timedelta(days=CN_LOOKBACK_DAYS), as_of)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_cn_analyst_fetch_failed", error=str(e))
        rows = []
    if not rows:  # 拉不到不覆盖旧缓存
        if redis is not None and refresh:
            try:
                if raw := await redis.get(CN_KEY):
                    return json.loads(raw)
            except Exception:  # noqa: BLE001
                pass
        return {}
    out = cn_actions_from_reports(rows)
    logger.info("signal_radar_cn_analyst_fetched", reports=len(rows), stocks=len(out),
                actions=sum(len(v) for v in out.values()))
    if redis is not None:
        try:
            await redis.set(CN_KEY, json.dumps(out, ensure_ascii=False), ex=CN_CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("signal_radar_cn_analyst_cache_write_failed", error=str(e))
    return out


# ---------- 港股：逐日快照比对 ----------

def diff_hk_ratings(
    state: dict[str, dict[str, str]], current: dict[str, dict[str, tuple[str, str | None]]], as_of: date,
) -> tuple[dict[str, dict[str, str]], dict[str, list[dict]]]:
    """上一份状态 {代码: {券商: 评级}} + 今天抓到的 {代码: {券商: (评级, 更新日期)}} → (新状态, 新事件)。

    第一次见到的股票 / 券商只记状态；今天没出现的券商保留旧状态（经济通偶尔少列几家）。
    """
    new_state = {code: dict(firms) for code, firms in state.items()}
    events: dict[str, list[dict]] = {}
    today = as_of.isoformat()
    floor = (as_of - timedelta(days=7)).isoformat()   # 更新日期早于一周前的，按今天记（是我们今天才看到的变化）
    for code, firms in current.items():
        old = state.get(code)
        dst = new_state.setdefault(code, {})
        for firm, (rating, updated) in firms.items():
            prev = old.get(firm) if old else None
            dst[firm] = rating
            action = _action(prev, rating) if prev else None
            if action is None:
                continue
            day = updated if updated and floor <= updated <= today else today
            events.setdefault(code, []).append(
                {"date": day, "firm": firm, "prev": prev or "", "new": rating, "action": action})
    return new_state, _sorted(events)


def merge_events(old: dict[str, list[dict]], new: dict[str, list[dict]], as_of: date) -> dict[str, list[dict]]:
    """合并事件、去重、丢掉 EVENT_KEEP_DAYS 天前的。"""
    cutoff = (as_of - timedelta(days=EVENT_KEEP_DAYS)).isoformat()
    out: dict[str, list[dict]] = {}
    for code in set(old) | set(new):
        seen: set[tuple] = set()
        lst = []
        for a in [*new.get(code, []), *old.get(code, [])]:
            k = (a["date"], a["firm"], a["prev"], a["new"])
            if a["date"] < cutoff or k in seen:
                continue
            seen.add(k)
            lst.append(a)
        if lst:
            out[code] = lst
    return _sorted(out)


def _text(v: object) -> str:
    return v.decode() if isinstance(v, bytes) else (str(v) if v is not None else "")


async def _json(redis: Redis, key: str) -> dict:
    raw = await redis.get(key)
    return json.loads(raw) if raw else {}


async def snapshot_hk(redis: Redis, codes: list[str], as_of: date) -> int | None:
    """给这些港股抓一次经济通券商评级并与上一份比对；当天已抓过返回 None，否则返回新事件数。"""
    from app.services.quant_research.cnhk import etnet
    from app.services.quant_research.cnhk.http import _UA

    today = as_of.isoformat()
    try:
        if _text(await redis.get(HK_DAY_KEY)) == today:
            return None
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_hk_analyst_day_read_failed", error=str(e))
        return None
    current: dict[str, dict[str, tuple[str, str | None]]] = {}
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": _UA}, trust_env=False) as client:
        for code in sorted({normalize_symbol("hk", c) for c in codes}):
            try:
                html = await etnet.fetch(client, code)
                fc = etnet.parse(html) if html else None
            except Exception as e:  # noqa: BLE001 单只失败跳过，明天再比
                logger.warning("signal_radar_hk_analyst_fetch_failed", symbol=code, error=str(e))
                continue
            if fc is None:
                continue
            firms: dict[str, tuple[str, str | None]] = {}
            for row in fc.rows:   # 评级只在第一财年那一行有
                if row.rating and row.firm and row.firm not in firms:
                    firms[row.firm] = (row.rating, row.updated.isoformat() if row.updated else None)
            if firms:
                current[code] = firms
    if len(current) < max(1, len(codes) // 2):   # 大面积抓不到（经济通繁忙）：不更新，下一轮再试
        logger.warning("signal_radar_hk_analyst_snapshot_incomplete", got=len(current), codes=len(codes))
        return 0
    state = await _json(redis, HK_STATE_KEY)
    new_state, events = diff_hk_ratings(state, current, as_of)
    merged = merge_events(await _json(redis, HK_EVENTS_KEY), events, as_of)
    await redis.set(HK_STATE_KEY, json.dumps(new_state, ensure_ascii=False), ex=HK_STATE_TTL)
    await redis.set(HK_EVENTS_KEY, json.dumps(merged, ensure_ascii=False), ex=HK_EVENTS_TTL)
    await redis.set(HK_DAY_KEY, today, ex=2 * 86400)
    if not await redis.get(HK_SINCE_KEY):
        await redis.set(HK_SINCE_KEY, today, ex=HK_EVENTS_TTL)
    else:
        await redis.expire(HK_SINCE_KEY, HK_EVENTS_TTL)
    n = sum(len(v) for v in events.values())
    logger.info("signal_radar_hk_analyst_snapshot", stocks=len(current), new_events=n)
    return n


async def hk_actions(redis: Redis | None) -> tuple[dict[str, list[dict]], str | None]:
    """港股累计的评级上调 / 下调 + 开始累计的日期。"""
    if redis is None:
        return {}, None
    try:
        since = _text(await redis.get(HK_SINCE_KEY))
        return await _json(redis, HK_EVENTS_KEY), (since or None)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_hk_analyst_read_failed", error=str(e))
        return {}, None


async def actions_for(market: str, redis: Redis | None, as_of: date) -> tuple[dict[str, list[dict]], str | None]:
    """{存储代码: 动作（新到旧）} + 港股开始累计的日期（A 股为 None）。"""
    if market == "cn":
        return await cn_actions(redis, as_of), None
    if market == "hk":
        return await hk_actions(redis)
    return {}, None


def today_local() -> date:
    """A 股 / 港股按北京时间算「今天」。"""
    return (datetime.now(UTC) + timedelta(hours=8)).date()
