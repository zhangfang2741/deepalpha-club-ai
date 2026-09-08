"""晨报 API 的 request/response schemas。"""

from datetime import date

from pydantic import BaseModel, Field

from app.services.morning_report.schema import MorningReportContent


class ReportMeta(BaseModel):
    """晨报元信息：市场/日期/生成状态/是否回退旧期。"""

    market: str
    trade_date: date | None = None
    status: str = Field(description="success / generating / pending / failed")
    stale: bool = False


class MorningReportResponse(BaseModel):
    """晨报获取接口响应体：generating/pending 时 content 为 None。"""

    meta: ReportMeta
    content: MorningReportContent | None = None


class ReportDatesResponse(BaseModel):
    """晨报历史日期列表响应体。"""

    market: str
    dates: list[date]


class DeviceTokenRequest(BaseModel):
    """APNs 设备 token 注册请求体。"""

    token: str = Field(min_length=20, description="APNs hex device token（真实为 64 位 hex）")
    locale: str = Field(default="zh-Hans", pattern="^(zh-Hans|en)$")


class AckResponse(BaseModel):
    """通用确认响应体。"""

    ok: bool = True
