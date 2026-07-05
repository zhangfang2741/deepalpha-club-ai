"""SEC filing 列表与分类 Pydantic schemas。"""

from typing import List

from pydantic import BaseModel, Field

from app.schemas.base import BaseResponse


class EightKItem(BaseResponse):
    code: str = Field(description="8-K item 代码，如 2.02")
    label: str = Field("", description="item 中文释义，未知代码为空")


class FilingRecord(BaseResponse):
    form: str = Field(description="SEC 表格类型，如 10-K / 8-K / 4")
    form_name: str = Field("", description="表格中文名，如 年报 / 季报（未知表格为空）")
    form_desc: str = Field("", description="表格中文解释（未知表格为空）")
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


class FilingDocument(BaseResponse):
    seq: str = Field("", description="文档序号")
    type: str = Field("", description="附件类型，如 EX-99.1 / 8-K")
    label: str = Field("", description="附件中文标签")
    description: str = Field("", description="附件原始描述（与类型重复时为空）")
    filename: str = Field(description="文档文件名")
    url: str = Field(description="文档直链")
    highlight: bool = Field(False, description="是否重点标出（如业绩新闻稿 EX-99.x）")


class FilingDocumentsResponse(BaseResponse):
    accession: str = Field(description="accession number")
    index_url: str = Field(description="filing 目录页链接")
    documents: List[FilingDocument] = Field(default_factory=list, description="该 filing 的文档/附件清单")


class CompanyProfile(BaseModel):
    """大模型生成的公司基础画像（结构化输出用）。

    面向投资者，帮助一眼建立对公司的基础认知与判断。所有内容用中文表述。
    """

    one_liner: str = Field(description="一句话概括公司是做什么的（不超过 40 字）")
    industry: str = Field(description="所属行业及细分赛道，一句话说明")
    supply_chain_position: str = Field(description="在产业链/供应链中的位置（上游/中游/下游），及上下游关系")
    main_products: List[str] = Field(default_factory=list, description="主要产品或业务线（3-6 项，每项简短）")
    main_customers: List[str] = Field(default_factory=list, description="主要客户或客户群体（3-6 项）")
    differentiation: str = Field(description="在行业中的核心差异化竞争力/护城河（2-3 句）")
    competitors: List[str] = Field(default_factory=list, description="主要竞争对手（3-6 家，公司名）")


class CompanyProfileResponse(BaseResponse):
    cik: str = Field(description="10 位补零 CIK")
    name: str = Field("", description="公司名称")
    ticker: str = Field("", description="股票代码")
    sic_description: str = Field("", description="行业 SIC 描述")
    profile: CompanyProfile = Field(description="大模型生成的公司基础画像")
