"""行业估值 z-score Pydantic schemas。"""

from typing import Any, Dict, List, Optional

from pydantic import Field

from app.schemas.base import BaseResponse


class SectorPERecord(BaseResponse):
    date: str = Field(description="季度日期，如 2024-09-30")
    pe: float = Field(description="当季 PE 比率")


class SectorValuation(BaseResponse):
    sector: str = Field(description="GICS 行业英文名")
    sector_cn: str = Field(description="行业中文名")
    etf_symbol: str = Field(description="SPDR 代理 ETF 代码")
    current_pe: Optional[float] = Field(None, description="最新季度 PE")
    hist_mean: Optional[float] = Field(None, description="历史 PE 均值")
    hist_std: Optional[float] = Field(None, description="历史 PE 标准差")
    z_score: Optional[float] = Field(None, description="当前 PE 的 z-score，相对于 10 年历史")
    label: str = Field(description="估值标签：极度低估/低估/中性/高估/极度高估/数据不足")
    label_en: str = Field(description="估值标签英文键")
    hist_pe: List[Dict[str, Any]] = Field(default_factory=list, description="历史 PE 季度序列 [{date, pe}]")
    data_quarters: int = Field(0, description="用于计算的历史季度数")


class SectorValuationResponse(BaseResponse):
    as_of: str = Field(description="最新数据日期")
    sectors: List[SectorValuation]


class ETFPricePoint(BaseResponse):
    date: str
    close: float


class ETFPriceResponse(BaseResponse):
    symbol: str
    prices: List[ETFPricePoint]
