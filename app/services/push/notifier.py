"""晨报生成推送编排：按 locale 分组发送，合并 cn+hk 为一条。

推送失败只记日志，绝不影响生成任务结果。
"""

import asyncio

from sqlmodel import select

from app.db.session import get_sync_session_cm
from app.models.device_token import DeviceToken

from app.core.logging import logger
from app.services.morning_report.schema import LocalizedText
from app.services.push import apns_client

TITLES: dict[str, dict[str, str]] = {
    "zh-Hans": {
        "us": "美股晨报已生成",
        "cn": "A股晨报已生成",
        "hk": "港股晨报已生成",
        "cn+hk": "A股 · 港股晨报已生成",
    },
    "en": {
        "us": "Your US Morning Brief is ready",
        "cn": "Your China A-share Morning Brief is ready",
        "hk": "Your HK Morning Brief is ready",
        "cn+hk": "Your China & HK Morning Briefs are ready",
    },
}


def _apns_configured() -> bool:
    return apns_client.is_configured()


def _load_tokens() -> list[dict]:
    """同步查全部设备 token（Celery 上下文，量小可接受）。"""
    with get_sync_session_cm() as session:
        rows = session.exec(select(DeviceToken)).all()
        return [{"token": r.token, "locale": r.locale} for r in rows]


async def _send_one(token: str, title: str, body: str, data: dict) -> bool:
    return await apns_client.send(token, title, body, data)


async def notify_generated(markets: list[str], summaries: dict[str, LocalizedText]) -> None:
    """按 markets 分组发送生成通知，markets 形如 ["us"] 或 ["cn","hk"]（合并为一条）；summaries 供正文。"""
    if not _apns_configured():
        logger.info("morning_report_push_skipped_not_configured")
        return
    sorted_markets = sorted(markets)
    primary_market = sorted_markets[0]
    key = "+".join(sorted_markets) if len(sorted_markets) > 1 else primary_market
    zh_summary = summaries[primary_market].zh if len(markets) == 1 else (
        "；".join(summaries[m].zh for m in sorted_markets)
    )
    en_summary = summaries[primary_market].en if len(markets) == 1 else (
        "; ".join(summaries[m].en for m in sorted_markets)
    )

    async def _send_to(row: dict) -> bool:
        locale = "zh-Hans" if row["locale"] != "en" else "en"
        title = TITLES[locale][key]
        body = zh_summary if locale == "zh-Hans" else en_summary
        return await _send_one(row["token"], title, body, {"market": primary_market})

    results = await asyncio.gather(*(_send_to(row) for row in await asyncio.to_thread(_load_tokens)))
    logger.info("morning_report_push_done", markets=markets, sent=sum(results))
