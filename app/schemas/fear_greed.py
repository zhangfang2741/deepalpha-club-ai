"""Fear & Greed Index Pydantic schemas."""
from typing import List, Optional

from pydantic import Field

from app.schemas.base import BaseResponse


class FearGreedPoint(BaseResponse):
    """历史数据中的单个数据点。"""

    date: str = Field(description="日期，格式 YYYY-MM-DD")
    score: float = Field(ge=0, le=100, description="恐慌贪婪指数分值 0–100")
    rating: str = Field(description="情绪标签，如 Extreme Fear / Fear / Neutral / Greed / Extreme Greed")


class FearGreedSnapshot(BaseResponse):
    """特定时间点的快照（当前/前一周/前一月/前一年/历史极值）。"""

    score: float = Field(ge=0, le=100)
    rating: str
    date: Optional[str] = Field(None, description="仅当前值、历史最高/最低时携带")


class FearGreedResponse(BaseResponse):
    """GET /api/v1/fear-greed 完整响应。"""

    current: FearGreedSnapshot
    previous_week: FearGreedSnapshot
    previous_month: FearGreedSnapshot
    previous_year: FearGreedSnapshot
    history_low: FearGreedSnapshot
    history_high: FearGreedSnapshot
    history: List[FearGreedPoint]
