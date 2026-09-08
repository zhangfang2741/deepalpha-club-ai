"""晨报表查询与 token upsert（异步，供 API 层调用）。"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.device_token import DeviceToken
from app.models.morning_report import MorningReport

BEIJING = ZoneInfo("Asia/Shanghai")


async def get_report(db: AsyncSession, market: str, report_date: date | None) -> tuple[MorningReport | None, bool]:
    """返回 (记录, 是否回退旧期)。无当日成功版 → 最近一期 success。

    注意用 SQLAlchemy 原生 `await db.execute()`（get_db 返回原生 AsyncSession，
    没有 SQLModel 扩展的 `.exec()`）；取 ORM 对象走 `.scalars()`。
    """
    if report_date is not None:
        record = (
            (await db.execute(
                select(MorningReport).where(
                    MorningReport.market == market,
                    MorningReport.trade_date == report_date,
                )
            ))
            .scalars()
            .first()
        )
        return record, False  # 指定日期不回退（历史页语义）

    # 「今日」按北京时间取，与生成任务（Celery）的 trade_date 口径一致；
    # 用 date.today()（服务器本地时区）在生产 UTC 环境会提前 8 小时切换日期，
    # 导致当日晨报被误标 stale。
    today = datetime.now(BEIJING).date()
    record = (
        (await db.execute(
            select(MorningReport).where(MorningReport.market == market, MorningReport.trade_date == today)
        ))
        .scalars()
        .first()
    )
    if record and record.status in ("success", "generating"):
        return record, False
    latest = (
        (await db.execute(
            select(MorningReport)
            .where(MorningReport.market == market, MorningReport.status == "success")
            .order_by(MorningReport.trade_date.desc())  # type: ignore[attr-defined]
        ))
        .scalars()
        .first()
    )
    return (latest, True) if latest else (None, False)


async def list_dates(db: AsyncSession, market: str, limit: int = 60) -> list[date]:
    """列出指定市场已成功生成的晨报日期（倒序，默认最多 60 条）。"""
    rows = (
        (await db.execute(
            select(MorningReport.trade_date)  # type: ignore[call-overload]
            .where(MorningReport.market == market, MorningReport.status == "success")
            .order_by(MorningReport.trade_date.desc())  # type: ignore[attr-defined]
            .limit(limit)
        ))
        .scalars()
        .all()
    )
    return list(rows)


async def upsert_token(db: AsyncSession, user_id: int, token: str, locale: str) -> None:
    """按 token 唯一约束 upsert 设备记录：已存在则更新归属用户与语言。"""
    existing = (
        (await db.execute(select(DeviceToken).where(DeviceToken.token == token)))
        .scalars()
        .first()
    )
    if existing:
        existing.user_id = user_id
        existing.locale = locale
        existing.last_user_id = user_id
        db.add(existing)
    else:
        db.add(DeviceToken(user_id=user_id, token=token, locale=locale, last_user_id=user_id))
    await db.commit()
