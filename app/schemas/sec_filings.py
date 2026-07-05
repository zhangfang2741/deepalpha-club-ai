"""SEC filing 列表与分类 Pydantic schemas。"""

from typing import List

from pydantic import Field

from app.schemas.base import BaseResponse


class EightKItem(BaseResponse):
    code: str = Field(description="8-K item 代码，如 2.02")
    label: str = Field("", description="item 中文释义，未知代码为空")


class FilingRecord(BaseResponse):
    form: str = Field(description="SEC 表格类型，如 10-K / 8-K / 4")
    category: str = Field(description="所属分类 key")
    filing_date: str = Field(description="提交日 YYYY-MM-DD")
    report_date: str = Field("", description="报告期日 YYYY-MM-DD（可能与提交日不同，也可能为空）")
    accession_number: str = Field(description="SEC accession number")
    primary_doc_description: str = Field("", description="主文档描述")
    items: List[EightKItem] = Field(default_factory=list, description="8-K item 明细，其他表格为空")
    index_url: str = Field("", description="SEC filing 目录页链接")
    doc_url: str = Field("", description="主文档直链")


class FilingCategory(BaseResponse):
    key: str = Field(description="分类 key")
    label: str = Field(description="分类中文标签")
    label_en: str = Field(description="分类英文标签")
    count: int = Field(description="该分类下 filing 数量")
    filings: List[FilingRecord] = Field(default_factory=list, description="该分类的 filing 列表（新→旧）")


class CompanyInfo(BaseResponse):
    cik: str = Field(description="10 位补零 CIK")
    name: str = Field("", description="公司名称")
    tickers: List[str] = Field(default_factory=list, description="股票代码列表")
    exchanges: List[str] = Field(default_factory=list, description="交易所列表")
    sic_description: str = Field("", description="行业 SIC 描述")


class CompanyFilingsResponse(BaseResponse):
    company: CompanyInfo
    total: int = Field(description="全部 filing 总数")
    categories: List[FilingCategory] = Field(default_factory=list, description="按分类分组的 filing")
