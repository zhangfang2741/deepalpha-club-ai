"""八字排盘与 AI 解读的请求/响应 schema。"""

from datetime import date, datetime, time
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import BaseResponse

_MIN_BIRTH_YEAR = 1900


class BaziChartRequest(BaseModel):
    birth_date: date = Field(description="阳历出生日期")
    birth_time: Optional[time] = Field(None, description="出生时间，None 表示时辰不确定")
    birth_city: str = Field(description="出生城市，用于真太阳时校正")
    gender: Literal["male", "female"] = Field(description="性别，决定大运顺逆排")

    @field_validator("birth_date")
    @classmethod
    def _birth_date_must_be_reasonable(cls, value: date) -> date:
        """拒绝未来日期和过于久远的日期，避免用户输入错误（如年份多打/少打一位）导致排盘结果无意义。"""
        if value > date.today():
            raise ValueError("出生日期不能晚于今天")
        if value.year < _MIN_BIRTH_YEAR:
            raise ValueError(f"出生日期不能早于 {_MIN_BIRTH_YEAR} 年")
        return value


class Pillar(BaseModel):
    gan: str = Field(description="天干")
    zhi: str = Field(description="地支")
    na_yin: str = Field(description="纳音")
    shi_shen_gan: str = Field(description="天干十神")
    shi_shen_zhi: List[str] = Field(description="地支藏干对应的十神列表")


class DaYunStep(BaseModel):
    gan_zhi: str = Field(description="大运干支")
    start_age: int = Field(description="起始虚岁")
    end_age: int = Field(description="结束虚岁")


class BaziChartResponse(BaseResponse):
    hour_known: bool = Field(description="出生时辰是否已知")
    solar_date: date = Field(description="阳历出生日期")
    lunar_date: str = Field(description="农历日期描述")
    true_solar_time: Optional[datetime] = Field(None, description="真太阳时校正后的时间，时辰未知时为 None")
    true_solar_time_applied: bool = Field(description="是否命中内置经度表并完成校正")
    year_pillar: Pillar
    month_pillar: Pillar
    day_pillar: Pillar
    time_pillar: Optional[Pillar] = Field(None, description="时柱，时辰未知时为 None")
    wu_xing_distribution: Dict[str, int] = Field(description="五行分布计数，键为 jin/mu/shui/huo/tu")
    da_yun: List[DaYunStep] = Field(description="大运表，共8步(80年)")
    liu_nian_gan_zhi: str = Field(description="当前年份的流年干支")


class InterpretationRequest(BaziChartRequest):
    section: Literal["daily", "deep"] = Field(description="daily=今日运势(免费) / deep=深度解读(付费)")


class InterpretationResponse(BaseResponse):
    text: str = Field(description="AI 生成的解读文本")
