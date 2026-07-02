"""FinReflectKG — 严格复刻论文的金融知识图谱构建模块。

论文：FinReflectKG — Agentic Construction and Evaluation of Financial
Knowledge Graphs（arXiv:2508.17906）。

模块组成：
- ontology：论文 Table 1/2 定义的实体与关系类型注册表（数据驱动，可补全）
- chunker：表格感知切片（table-aware chunking）
- prompts：schema-guided 抽取 / 评审 / 修正提示词
- checkrules：规则化合规策略（CheckRules）与合规率
- graph：LangGraph 编排的三种抽取模式（single_pass / multi_pass / reflection）
"""

from app.services.graph.finreflect.chunker import chunk_document
from app.services.graph.finreflect.checkrules import (
    check_triple,
    compliance_score,
)
from app.services.graph.finreflect.graph import extract_triples
from app.services.graph.finreflect.ontology import (
    ENTITY_TYPES,
    RELATION_TYPES,
)

__all__ = [
    "ENTITY_TYPES",
    "RELATION_TYPES",
    "check_triple",
    "chunk_document",
    "compliance_score",
    "extract_triples",
]
