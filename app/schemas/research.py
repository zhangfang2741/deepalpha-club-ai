"""行业研究 Agent 的结构化输出 schema."""

from typing import List, Optional

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """单条搜索证据。"""

    snippet: str = Field(description="搜索结果摘录或关键事实")
    source: str = Field(description="来源 URL 或 'DuckDuckGo: <query>'")


class IndustryUnderstanding(BaseModel):
    """Step 1：理解行业。"""

    description: str = Field(description="行业精准定义，2-3句")
    main_products: List[str] = Field(description="核心产品或服务类别")
    key_customers: List[str] = Field(description="主要客户群体类型")
    development_stage: str = Field(description="当前发展阶段（萌芽/成长/成熟/衰退）及理由")
    what: str = Field(description="一句话说明该行业是什么")
    why: str = Field(description="一句话说明理解该行业为何重要")
    evidence: List[EvidenceItem] = Field(default_factory=list)


class WhyItExists(BaseModel):
    """Step 2：行业存在原因与驱动力。"""

    tech_drivers: List[str] = Field(description="技术驱动因素")
    policy_drivers: List[str] = Field(description="政策/监管驱动因素")
    demand_drivers: List[str] = Field(description="需求侧驱动因素")
    cost_drivers: List[str] = Field(description="成本结构变化驱动因素")
    what: str = Field(description="一句话总结核心驱动力")
    why: str = Field(description="一句话说明这些驱动力为何重要")
    evidence: List[EvidenceItem] = Field(default_factory=list)


class ChainLevel(BaseModel):
    """产业链单个环节。"""

    level: str = Field(description="上游/中游/下游")
    description: str = Field(description="该环节的简要描述")
    key_players: List[str] = Field(description="代表性公司或参与者类型")


class IndustryChain(BaseModel):
    """Step 3：产业链结构。"""

    upstream: ChainLevel
    midstream: ChainLevel
    downstream: ChainLevel
    what: str = Field(description="一句话总结产业链核心结构")
    why: str = Field(description="一句话说明理解产业链对投资者的意义")
    evidence: List[EvidenceItem] = Field(default_factory=list)


class KeyBottlenecks(BaseModel):
    """Step 4：核心瓶颈与定价权。"""

    bottlenecks: List[str] = Field(description="制约行业发展的核心瓶颈")
    pricing_power: str = Field(description="谁拥有定价权及原因")
    most_profitable_segment: str = Field(description="当前最赚钱的产业链环节及逻辑")
    what: str = Field(description="一句话总结最关键瓶颈")
    why: str = Field(description="一句话说明这对投资者的意义")
    evidence: List[EvidenceItem] = Field(default_factory=list)


class LeadingCompany(BaseModel):
    """单家龙头公司信息。"""

    name: str
    ticker: Optional[str] = Field(default=None, description="股票代码，如 NVDA")
    business: str = Field(description="主营业务，50字以内")
    moat: str = Field(description="核心护城河来源")


class LeadingCompanies(BaseModel):
    """Step 5：行业龙头企业。"""

    companies: List[LeadingCompany] = Field(description="行业主要公司，3-6家")
    what: str = Field(description="一句话总结行业竞争格局")
    why: str = Field(description="一句话说明这些公司为何值得关注")
    evidence: List[EvidenceItem] = Field(default_factory=list)


class BusinessModel(BaseModel):
    """Step 6：行业商业模式。"""

    revenue_model: str = Field(description="行业典型收入来源和模式")
    cost_structure: str = Field(description="主要成本构成")
    profit_drivers: str = Field(description="利润驱动因素")
    moat_sources: List[str] = Field(description="护城河来源列表")
    what: str = Field(description="一句话总结商业模式本质")
    why: str = Field(description="一句话说明商业模式对估值的影响")
    evidence: List[EvidenceItem] = Field(default_factory=list)


class InvestmentView(BaseModel):
    """Step 7：投资观点。"""

    opportunities: List[str] = Field(description="具体投资机会（催化剂、时间窗口）")
    risks: List[str] = Field(description="主要风险（系统性/行业特有）")
    focus_areas: List[str] = Field(description="投资者重点关注的指标或方向")
    conclusion: str = Field(description="100字以内的综合投资观点")
    what: str = Field(description="一句话总结投资逻辑")
    why: str = Field(description="一句话说明当前时点的特殊性")
    evidence: List[EvidenceItem] = Field(default_factory=list)


class IndustryResearchRequest(BaseModel):
    """行业研究请求体。"""

    industry: str = Field(min_length=1, max_length=100, description="行业名称，如'半导体'、'新能源汽车'")
