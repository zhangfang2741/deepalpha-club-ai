"""CheckRules — 规则化合规策略（rule-based policies）。

论文评估体系的规则层：用确定性策略批量审计抽取三元组，
计算合规率（compliance，论文中反思模式达 64.8%）。
规则检查用于**评估与标注**，不参与反思循环内部（循环内的评审由 Critic LLM 承担）。

四条策略：
    P1 entity_type_policy   头/尾实体类型必须属于本体
    P2 relation_policy      关系类型必须属于本体
    P3 well_formed_policy   头/尾实体非空、非自环、名称长度合理
    P4 grounding_policy     证据句非空且能在原文 chunk 中接地
"""

from typing import Any

from app.services.graph.finreflect.ontology import is_valid_entity_type, is_valid_relation

# 证据接地阈值：证据词与原文词重合比例下限（宽松，容忍轻度改写）
_GROUNDING_MIN_OVERLAP = 0.5
_MAX_ENTITY_NAME_LEN = 120


def _tokenize(text: str) -> set[str]:
    """粗粒度分词：小写、按非字母数字切分，用于接地重合度估算。"""
    return {tok for tok in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(tok) > 1}


def check_triple(triple: dict[str, Any], chunk_text: str) -> list[str]:
    """对单条 5 元组执行全部策略，返回违规信息列表（空列表 = 合规）。"""
    violations: list[str] = []

    head = str(triple.get("head", "")).strip()
    tail = str(triple.get("tail", "")).strip()
    head_type = str(triple.get("head_type", "")).strip()
    tail_type = str(triple.get("tail_type", "")).strip()
    relation = str(triple.get("relation", "")).strip()
    evidence = str(triple.get("evidence", "")).strip()

    # P3 well_formed_policy
    if not head or not tail:
        violations.append("well_formed_policy: 头/尾实体名为空")
    if head and tail and head.lower() == tail.lower():
        violations.append(f"well_formed_policy: 自环三元组 '{head}' 指向自身")
    if len(head) > _MAX_ENTITY_NAME_LEN or len(tail) > _MAX_ENTITY_NAME_LEN:
        violations.append("well_formed_policy: 实体名称过长，疑似整句被当作实体")

    # P1 entity_type_policy
    if not is_valid_entity_type(head_type):
        violations.append(f"entity_type_policy: 头实体类型 '{head_type}' 不在本体中")
    if not is_valid_entity_type(tail_type):
        violations.append(f"entity_type_policy: 尾实体类型 '{tail_type}' 不在本体中")

    # P2 relation_policy
    if not is_valid_relation(relation):
        violations.append(f"relation_policy: 关系 '{relation}' 不在本体中")

    # P4 grounding_policy
    if not evidence:
        violations.append("grounding_policy: 缺少原文证据句")
    elif chunk_text:
        ev_tokens = _tokenize(evidence)
        if ev_tokens:
            overlap = len(ev_tokens & _tokenize(chunk_text)) / len(ev_tokens)
            if overlap < _GROUNDING_MIN_OVERLAP:
                violations.append(
                    f"grounding_policy: 证据与原文词重合仅 {overlap:.0%}，疑似臆造"
                )

    return violations


def annotate_compliance(
    triples: list[dict[str, Any]],
    chunk_text: str,
) -> list[dict[str, Any]]:
    """就地为每条三元组标注 ``compliant`` 与 ``violations`` 字段并返回。"""
    for triple in triples:
        violations = check_triple(triple, chunk_text)
        triple["violations"] = violations
        triple["compliant"] = not violations
    return triples


def compliance_score(triples: list[dict[str, Any]], chunk_text: str) -> float:
    """合规率：通过全部策略的三元组占比。"""
    if not triples:
        return 1.0
    passed = sum(1 for t in triples if not check_triple(t, chunk_text))
    return passed / len(triples)
