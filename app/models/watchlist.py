"""自选股：用户手动关注的标的清单，供「自选」Tab 与分析详情页加入/删除按钮共用。"""

from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.types import DateTime
from sqlmodel import Field

from app.db.base import UUIDModel


def _utcnow() -> datetime:
    """UTC-aware 当前时间。供 created_at/updated_at 默认值使用。"""
    return datetime.now(UTC)


class WatchlistItem(UUIDModel, table=True):
    """一条自选股记录：一个用户对同一 (market, symbol) 只保留一条。

    时间列显式声明 timezone=True（timestamptz）：本表经异步 asyncpg 写入
    （API 层直接 insert/delete），UUIDModel 默认的 aware datetime 写 naive 列
    会直接抛 asyncpg DataError（同 DeviceToken 的做法）。
    """

    __tablename__: ClassVar[str] = "watchlist_item"  # pyright: ignore[reportIncompatibleVariableOverride]
    __table_args__ = (
        UniqueConstraint("user_id", "market", "symbol", name="uq_watchlist_user_market_symbol"),
    )

    user_id: int = Field(foreign_key="user.id", index=True)
    market: str = Field(description="us / cn / hk")
    symbol: str = Field(index=True, description="裸代码，不带市场后缀")
    name: str = Field(description="展示用名称")
    # 示例自选：每个用户默认送的美/A/港龙头（见 app/services/watchlist.py SAMPLE_ITEMS），
    # 不占订阅档名额。用户删除示例股时只置 hidden，不真删——留着这条记录才知道「送过了」，
    # 不会下次打开又补回来。
    is_sample: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})
    hidden: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})

    created_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(  # type: ignore[assignment]
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=_utcnow),
    )
