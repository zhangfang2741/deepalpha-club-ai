"""CheckRules — 论文 5.1 节定义的四条规则化合规检查。

对每条抽取三元组独立评估以下四条规则（论文原版规则集）：

    R1 subject_reference        头/尾实体不得是缺乏语义指向的抽象指代
                                （如 "the company" / "we" / "our" / "it"，
                                应规范化为具体实体，如 "AAPL"）
    R2 entity_length            实体名不超过 5 个词，防止冗长表述
    R3 entity_schema            头/尾实体类型必须属于预配置 schema
    R4 relationship_schema      关系类型必须属于预配置 schema

单条三元组得分 CR(t) = 通过规则数 / 规则总数（论文式 9）；
合规率 compliance_score = 通过全部四条规则的三元组占比
（对应论文 Table 4 的 "At least 4 rules"，反思模式为 64.8%）。

规则检查用于评估与标注，不参与反思循环内部（循环内评审由 Critic LLM 承担）。
"""

from typing import Any

from app.services.graph.finreflect.ontology import is_valid_entity_type, is_valid_relation

# R1：抽象指代黑名单（小写精确匹配）
_ABSTRACT_REFERENCES = {
    "the company", "company", "we", "our", "us", "it", "its",
    "the firm", "the registrant", "the issuer",
}

# R2：实体名最大词数
_MAX_ENTITY_WORDS = 5

RULE_COUNT = 4


def check_triple(triple: dict[str, Any], chunk_text: str = "") -> list[str]:
    """对单条 5 元组执行四条规则，返回违规信息列表（空列表 = 全部通过）。

    Args:
        triple: 论文 5 元组 dict（head/head_type/relation/tail/tail_type）。
        chunk_text: 保留参数（规则集不依赖原文，接口与调用方兼容）。
    """
    violations: list[str] = []

    head = str(triple.get("head", "")).strip()
    tail = str(triple.get("tail", "")).strip()
    head_type = str(triple.get("head_type", "")).strip()
    tail_type = str(triple.get("tail_type", "")).strip()
    relation = str(triple.get("relation", "")).strip()

    # R1 subject_reference：抽象指代（空名称同样无语义指向，一并计入）
    for label, name in (("头", head), ("尾", tail)):
        if not name or name.lower() in _ABSTRACT_REFERENCES:
            violations.append(
                f"subject_reference: {label}实体 '{name}' 是抽象指代或为空，应规范化为具体实体（如 ticker）"
            )

    # R2 entity_length：不超过 5 个词
    for label, name in (("头", head), ("尾", tail)):
        if len(name.split()) > _MAX_ENTITY_WORDS:
            violations.append(
                f"entity_length: {label}实体 '{name[:60]}…' 超过 {_MAX_ENTITY_WORDS} 个词"
            )

    # R3 entity_schema：实体类型 ∈ schema
    if not is_valid_entity_type(head_type):
        violations.append(f"entity_schema: 头实体类型 '{head_type}' 不在预配置 schema 中")
    if not is_valid_entity_type(tail_type):
        violations.append(f"entity_schema: 尾实体类型 '{tail_type}' 不在预配置 schema 中")

    # R4 relationship_schema：关系 ∈ schema
    if not is_valid_relation(relation):
        violations.append(f"relationship_schema: 关系 '{relation}' 不在预配置 schema 中")

    return violations


def checkrules_score(triple: dict[str, Any]) -> float:
    """单条三元组的 CheckRules 得分 CR(t) = 通过规则数 / 4（论文式 9）。"""
    violations = check_triple(triple)
    violated_rules = {v.split(":", 1)[0] for v in violations}
    return (RULE_COUNT - len(violated_rules)) / RULE_COUNT


def annotate_compliance(
    triples: list[dict[str, Any]],
    chunk_text: str = "",
) -> list[dict[str, Any]]:
    """就地为每条三元组标注 ``compliant`` / ``violations`` / ``checkrules_score``。"""
    for triple in triples:
        violations = check_triple(triple, chunk_text)
        triple["violations"] = violations
        triple["compliant"] = not violations
        triple["checkrules_score"] = checkrules_score(triple)
    return triples


def compliance_score(triples: list[dict[str, Any]], chunk_text: str = "") -> float:
    """合规率：通过全部四条规则的三元组占比（论文 Table 4 口径）。"""
    if not triples:
        return 1.0
    passed = sum(1 for t in triples if not check_triple(t, chunk_text))
    return passed / len(triples)
