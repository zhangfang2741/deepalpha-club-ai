"""机构资金信号每日快照。

用于把「水平」信号升级为「变化率」信号：
- 预期：EPS/营收一致预期的 30/60/90 天修正趋势
- 仓位：期权 OI 变化率、IV Rank（需 ~1 年 IV 历史）

每支标的每天一行（symbol + snapshot_date 唯一）。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.db.base import UUIDModel


class SignalSnapshot(UUIDModel, table=True):
    """机构资金信号每日快照（每支标的每天一行）。"""

    __tablename__ = "signal_snapshots"
    __table_args__ = (
        UniqueConstraint("symbol", "snapshot_date", name="uq_signal_snapshot"),
    )

    symbol: str = Field(..., max_length=20, index=True, nullable=False)
    snapshot_date: str = Field(..., max_length=10, index=True, nullable=False)

    # 预期：分析师一致预期（用于修正趋势）
    eps_estimate: Optional[float] = Field(default=None)
    revenue_estimate: Optional[float] = Field(default=None)
    price_target_avg: Optional[float] = Field(default=None)

    # 仓位：期权快照（用于 OI 变化率、IV Rank）
    call_oi: Optional[int] = Field(default=None)
    put_oi: Optional[int] = Field(default=None)
    call_vol: Optional[int] = Field(default=None)
    put_vol: Optional[int] = Field(default=None)
    atm_iv: Optional[float] = Field(default=None)
