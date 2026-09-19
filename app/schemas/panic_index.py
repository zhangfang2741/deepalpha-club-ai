"""三地恐慌指数（美股 VIX / A股 50ETF-QVIX / 港股 VHSI）Pydantic schemas。

三个市场原始量纲不同（VIX 与美股 Fear & Greed 已经是 0~100 分；QVIX / VHSI
是波动率百分比，量级 10~40），统一折算成与 CNN Fear & Greed 同语义的
0~100 分（越低越恐慌、越高越贪婪），供前端用同一套卡片/曲线组件展示三地。
折算规则见 app/services/panic_index.py 的 _vol_to_score。
"""
from typing import List, Optional

from pydantic import Field

from app.schemas.base import BaseResponse


class PanicIndexPoint(BaseResponse):
    """历史数据中的单个数据点。"""

    date: str = Field(description="日期，格式 YYYY-MM-DD")
    score: float = Field(ge=0, le=100, description="恐慌贪婪分数 0~100（越低越恐慌）")
    rating: str = Field(description="情绪标签：Extreme Fear / Fear / Neutral / Greed / Extreme Greed")
    raw_value: Optional[float] = Field(None, description="原始指标值（VIX/QVIX/VHSI 点位），仅供参考展示")


class PanicIndexSnapshot(BaseResponse):
    """特定时间点的快照（当前/前一周/前一月）。"""

    score: float = Field(ge=0, le=100)
    rating: str
    date: Optional[str] = Field(None, description="仅当前值携带")
    raw_value: Optional[float] = None


class PanicIndexResponse(BaseResponse):
    """GET /api/v1/panic-index 完整响应。"""

    market: str = Field(description="us / cn / hk")
    label: str = Field(description="展示名称，如「VIX 恐慌指数」「中国波指 (50ETF QVIX)」")
    current: PanicIndexSnapshot
    previous_week: PanicIndexSnapshot
    previous_month: PanicIndexSnapshot
    history: List[PanicIndexPoint]
