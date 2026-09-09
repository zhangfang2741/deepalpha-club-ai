"""晨报生成 Celery 任务：幂等、逐市场串行、成功后按组推送。"""

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlmodel import select

from app.core.celery_app import celery_app
from app.core.logging import logger
from app.db.session import get_sync_session_cm
from app.models.morning_report import MorningReport
from app.services.morning_report.generator import generate_report
from app.services.morning_report.schema import LocalizedText
from app.services.push.notifier import notify_generated

BEIJING = ZoneInfo("Asia/Shanghai")


async def _generate_one(market: str, trade_date: date) -> dict:
    """生成单个市场的晨报并落库，失败也落库（status=failed），不向上抛异常。

    注意：不用 `session.get(MorningReport, record_id)` 重新查询来更新状态——
    这里在同一个函数作用域内直接持有 `record` 对象引用，跨 `with` 块复用同一个
    Python 对象来改字段再 add，天然规避了「用新 session 按 id 重新查询」这一步。
    """
    with get_sync_session_cm() as session:
        existing = session.exec(
            select(MorningReport).where(
                MorningReport.market == market, MorningReport.trade_date == trade_date
            )
        ).first()
        if existing and existing.status == "success":
            return {"market": market, "skipped": True, "status": "success"}
        record = existing or MorningReport(market=market, trade_date=trade_date)
        record.status = "generating"
        record.error = None
        session.add(record)
        session.commit()

    try:
        content, meta = await generate_report(market, trade_date.isoformat())
        if content is None:
            # 正常链路应已被 write() 挡住（None 会被转成异常）；这里是防御性
            # 兜底——不管 generate_report 因为什么原因返回空内容，都不能让
            # 下面的 model_dump() 崩溃到 try 之外，导致记录永远卡在 generating。
            raise ValueError("generate_report 返回了空内容")
        record.status = "success"
        record.content = content.model_dump()
        record.generated_at = datetime.now(BEIJING)
        record.model_name = meta.get("model_name")
        record.duration_ms = meta.get("duration_ms")
        with get_sync_session_cm() as session:
            session.add(record)
            session.commit()
        return {"market": market, "status": "success", "summary": content.summary}
    except Exception as exc:  # noqa: BLE001 —— 失败落库，不让单市场炸掉整批
        logger.exception("morning_report_generate_failed", market=market)
        record.status = "failed"
        record.error = str(exc)[:2000]
        with get_sync_session_cm() as session:
            session.add(record)
            session.commit()
        return {"market": market, "status": "failed"}


async def _generate(markets: list[str]) -> dict:
    """按市场串行生成：已存在成功记录的市场直接跳过，其余调用 _generate_one。

    幂等检查放在这里（而不是完全依赖 _generate_one 内部的检查），这样已成功的
    市场不会触发任何生成相关的调用；_generate_one 内部的检查作为独立调用时的
    第二道保险保留。
    """
    trade_date = datetime.now(BEIJING).date()
    results: dict[str, dict] = {}
    summaries: dict[str, LocalizedText] = {}
    for market in markets:
        with get_sync_session_cm() as session:
            existing = session.exec(
                select(MorningReport).where(
                    MorningReport.market == market, MorningReport.trade_date == trade_date
                )
            ).first()
        if existing and existing.status == "success":
            results[market] = {"market": market, "skipped": True, "status": "success"}
            continue
        result = await _generate_one(market, trade_date)
        results[market] = {key: value for key, value in result.items() if key != "summary"}
        if result.get("status") == "success" and not result.get("skipped"):
            summaries[market] = result["summary"]
    if summaries:
        try:
            await notify_generated(list(summaries), summaries)
        except Exception:  # noqa: BLE001 —— 推送失败不影响任务结果
            logger.exception("morning_report_push_failed")
    return results


@celery_app.task(name="morning_report.generate")
def generate_reports(markets: list[str]) -> dict:
    """Beat 入口：["us"] 06:30 / ["cn","hk"] 07:10（北京时间）。"""
    return asyncio.run(_generate(markets))
