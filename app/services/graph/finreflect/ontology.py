"""FinReflectKG 本体注册表 — 论文 Table 1/2 定义的实体与关系类型。

论文完整本体为 24 类实体、29 类关系（面向 SEC 10-K 年报抽取）。
本注册表当前收录已核实的 21 类实体与 22 类关系（来源：论文衍生工作
FinReflectKG-MultiHop（arXiv:2510.02906）正文/模式示例与开源数据集文档）；
类型名称与论文一致，描述为本项目自行撰写的简述。
剩余条目核实后直接在下方两个字典中追加即可（数据驱动，无需改动其他代码）。

三元组格式（论文 5 元组）：
    (Head Entity, Head Type, Relationship, Tail Entity, Tail Type) + 原文证据
"""

# ── 实体类型（Table 1）────────────────────────────────────────────────────────
# key: 论文中的类型名；value: 面向抽取提示词的英文简述（自行撰写）
ENTITY_TYPES: dict[str, str] = {
    "ORG": "The filing company itself — the registrant that filed this 10-K",
    "COMP": "Any other company mentioned in the filing: competitor, supplier, customer, or partner",
    "ORG_GOV": "Government bodies or agencies (e.g., U.S. Government, Congress)",
    "ORG_REG": "Domestic or international regulatory bodies (e.g., SEC, Federal Reserve, ECB)",
    "PERSON": "Named individuals, typically executives or board members (e.g., CEO, CFO)",
    "GPE": "Geopolitical entities: countries, states, or cities tied to operations or risks",
    "SECTOR": "Industries or sectors relevant to the filer or mentioned companies (e.g., Technology, Healthcare)",
    "PRODUCT": "Products or services offered or referenced (e.g., iPhone, AWS)",
    "EVENT": "Material events such as M&A deals, pandemics, natural disasters, or product launches",
    "RISK_FACTOR": "Disclosed risks (e.g., market risk, supply chain risk, cybersecurity risk, geopolitical risk)",
    "FIN_METRIC": "Financial metrics or values (e.g., Net Income, EBITDA, Long-Term Debt, CapEx, R&D Expense)",
    "ESG_TOPIC": "Environmental, social, and governance themes (e.g., Carbon Emissions, DEI, Climate Risk)",
    "MACRO_CONDITION": "Qualitative macroeconomic trends affecting the company or industry (e.g., Recession, Inflationary Pressures, Labor Shortages)",
    "ECON_IND": "Quantitative economic indicators (e.g., Inflation Rate, GDP Growth, Unemployment Rate, Interest Rate)",
    "FIN_INST": "Tradable financial instruments — assets or liabilities (e.g., bonds, derivatives, options)",
    "CONCEPT": "Abstract concepts, themes, or technologies (e.g., Artificial Intelligence, Digital Transformation)",
    "REGULATORY_REQUIREMENT": "Specific regulations or legal frameworks (e.g., Basel III, SEC rules, GDPR)",
    "LITIGATION": "Lawsuits or legal proceedings the company is party to",
    "ACCOUNTING_POLICY": "Accounting standards or policies applied in the filing (e.g., ASC standards, revenue recognition)",
    "RAW_MATERIAL": "Critical raw materials or commodity inputs the company relies on (e.g., lithium, semiconductors, crude oil)",
    "FIN_MARKET": "Financial markets or market indices (e.g., S&P 500, bond market, commodity markets)",
}

# ── 关系类型（Table 2）────────────────────────────────────────────────────────
RELATION_TYPES: dict[str, str] = {
    "Has_Stake_In": "Holds full or partial ownership or an equity interest in the tail entity",
    "Announces": "Publicly discloses or communicates the tail entity (plan, result, event)",
    "Introduces": "Rolls out or implements a new product, policy, or business segment",
    "Produces": "Manufactures, develops, or delivers a product or service",
    "Supplies": "Acts as a vendor or supplier to the tail entity",
    "Partners_With": "Maintains a formal or strategic collaboration with the tail entity",
    "Invests_In": "Allocates capital or resources into the tail entity",
    "Operates_In": "Has operational, geographic, or market presence in the tail entity",
    "Regulates": "Exerts control or regulatory oversight over the tail entity",
    "Involved_In": "Directly participates in an event such as a merger, acquisition, or litigation",
    "Impacts": "Broadly influences or affects the tail entity",
    "Impacted_By": "Is materially affected by the tail entity (event or condition)",
    "Positively_Impacts": "Has a beneficial causal effect on the tail entity (e.g., ESG_TOPIC → FIN_METRIC)",
    "Negatively_Impacts": "Has an adverse causal effect on the tail entity (e.g., RISK_FACTOR → FIN_METRIC)",
    "Discloses": "Reports or reveals the tail entity in the filing (risk, metric, policy)",
    "Depends_On": "Relies on the tail entity (supplier, technology, market, resource)",
    "Related_To": "Generic association when no more specific relation applies",
    "Faces": "Encounters a legal or regulatory challenge (e.g., ORG → LITIGATION)",
    "Complies_With": "Meets a regulatory or policy requirement (e.g., ORG → REGULATORY_REQUIREMENT)",
    "Subject_To": "Is governed or bound by the tail entity (e.g., ORG → ACCOUNTING_POLICY)",
    "Causes_Shortage_Of": "Triggers a supply shortage of the tail entity (e.g., EVENT → RAW_MATERIAL)",
    "Market_Reacts_To": "Links a condition or event to a financial market reaction (e.g., MACRO_CONDITION → FIN_MARKET)",
}


def is_valid_entity_type(name: str) -> bool:
    """判断实体类型是否属于本体。"""
    return name in ENTITY_TYPES


def is_valid_relation(name: str) -> bool:
    """判断关系类型是否属于本体。"""
    return name in RELATION_TYPES


def render_entity_types() -> str:
    """将实体类型渲染为提示词中的列表文本。"""
    return "\n".join(f"- {name}: {desc}" for name, desc in ENTITY_TYPES.items())


def render_relation_types() -> str:
    """将关系类型渲染为提示词中的列表文本。"""
    return "\n".join(f"- {name}: {desc}" for name, desc in RELATION_TYPES.items())
