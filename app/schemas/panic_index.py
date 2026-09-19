"""三地恐慌指数（美股 VIX / A股上证指数 / 港股恒生指数）Pydantic schemas。

美股沿用 CNN Fear & Greed 官方合成分（已经是 0~100 分）；A股/港股用指数收盘价
算 RSI(14) 直接当分数（RSI 天然 0~100，越高越贪婪、越低越恐慌），统一折算成
同语义的 0~100 分，供前端用同一套卡片/曲线组件展示三地。
折算规则见 app/services/panic_index.py 的 _price_to_points。
"""
from typing import List, Optional

from pydantic import Field

from app.schemas.base import BaseResponse


class PanicIndexPoint(BaseResponse):
    """历史数据中的单个数据点。"""

    date: str = Field(description="日期，格式 YYYY-MM-DD")
    score: float = Field(ge=0, le=100, description="恐慌贪婪分数 0~100（越低越恐慌）")
    rating: str = Field(description="情绪标签：Extreme Fear / Fear / Neutral / Greed / Extreme Greed")
    raw_value: Optional[float] = Field(None, description="原始指标值（cn/hk 为指数收盘点位，us 恒为空），仅供参考展示")


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
