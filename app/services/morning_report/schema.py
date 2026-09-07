"""晨报内容 schema——一套定义三用：LLM 结构化输出约束、存库校验、API 返回体。

双语采用叶子级 LocalizedText：每个文本字段自带 zh/en 两份，数字/symbol/结构单份，
两版判断天然一致，LLM 输出 token 比整树双份省一半。
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Direction = Literal["up", "down", "flat"]
MarketCode = Literal["us", "cn", "hk"]
SECTION_KEYS: tuple[str, ...] = (
    "pricing_gap",
    "earnings_valuation",
    "industry_chain",
    "crowding_risk",
)


class LocalizedText(BaseModel):
    """叶子级双语文本。zh 必填；en 必填非空（英文版不许悄悄缺失）。"""

    zh: str = Field(min_length=1, description="简体中文")
    en: str = Field(min_length=1, description="English")


class Metric(BaseModel):
    name: LocalizedText
    value: str = Field(description="展示值，如 -1.2% / 18.4")
    direction: Direction
    note: LocalizedText


class SectionEntry(BaseModel):
    """四层信息结构——晨报的灵魂，每条目固定四层。"""

    fact: LocalizedText = Field(description="事实依据：具体数字/事件")
    insight: LocalizedText = Field(description="细节洞察：市场定价与预期差")
    prediction: LocalizedText = Field(description="未来预测：必须带时间范围")
    verification: LocalizedText = Field(description="验证或反证信号：可跟踪口径")


class Section(BaseModel):
    key: Literal["pricing_gap", "earnings_valuation", "industry_chain", "crowding_risk"]
    title: LocalizedText
    entries: list[SectionEntry] = Field(min_length=1, max_length=3)


class StockPick(BaseModel):
    symbol: str = Field(description="NVDA / 0700 / 600519，供 App 跳转分析页")
    name: LocalizedText
    change_pct: str
    direction: Direction
    bull: LocalizedText = Field(description="看多情形 + 关键价格/条件")
    base: LocalizedText = Field(description="基准情形")
    bear: LocalizedText = Field(description="看空情形")


class Catalyst(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
    event: LocalizedText
    why: LocalizedText
    market: MarketCode


class MorningReportContent(BaseModel):
    headline: LocalizedText = Field(description="今日核心判断，1-2 句")
    summary: LocalizedText = Field(description="一句话摘要，推送正文用")
    metrics: list[Metric] = Field(min_length=3, max_length=3, description="恰好 3 个关键指标卡")
    sections: list[Section] = Field(min_length=4, max_length=4)
    stocks: list[StockPick] = Field(min_length=2, max_length=3)
    catalysts: list[Catalyst] = Field(min_length=3, max_length=6)

    @model_validator(mode="before")
    @classmethod
    def _validate_sections_keys(cls, data: object) -> object:
        """在字段级长度校验之前先检查 key 齐全性/重复性，给出可定位的中文错误信息。

        字段级 Field(min_length=4, max_length=4) 仍保留作为双重保险：
        若未来 Literal 新增第 5 个 key 导致本校验逻辑失效，长度约束能兜底拦截。
        """
        if not isinstance(data, dict):
            return data
        sections = data.get("sections")
        if not isinstance(sections, list):
            return data
        keys = [s.get("key") if isinstance(s, dict) else getattr(s, "key", None) for s in sections]
        if len(set(keys)) != len(keys):
            raise ValueError("模块 key 重复")
        for required in SECTION_KEYS:
            if required not in keys:
                raise ValueError(f"缺少模块 {required}，四个分析模块必须齐全")
        return data
