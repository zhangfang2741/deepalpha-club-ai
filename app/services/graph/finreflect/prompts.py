"""FinReflectKG 提示词 — schema-guided 抽取 / 规范化 / 评审 / 修正。

对应论文 4.3 节三种工作流：
- single_pass：单一综合提示词一步抽取（式 1）
- multi_pass：抽取后第二遍以专用规范化提示词精炼（式 2-3）
- reflection：Feedback LLM 产出逐三元组结构化反馈（Box 4.1 格式），
  Correction LLM 修订或删除问题三元组（式 4-6）

所有提示词将本体（ontology.py）动态渲染进上下文，
输出统一为论文 5 元组 + 原文证据的 JSON：

    {"triples": [{"head": ..., "head_type": ..., "relation": ...,
                  "tail": ..., "tail_type": ..., "evidence": ...}]}
"""

import json
from typing import Any

from app.services.graph.finreflect.ontology import render_entity_types, render_relation_types

# 提示词角色标记（测试与调试用，勿随意改动）
CORRECTOR_MARKER = "You MUST address every feedback item"
NORMALIZE_MARKER = "normalization pass"


def build_extraction_system_prompt() -> str:
    """schema-guided 抽取系统提示词（本体动态注入，论文 4.3.1）。"""
    return f"""You are a financial knowledge-graph extraction agent. You read a chunk of a company's SEC 10-K annual report and extract knowledge triples in the form (head entity, head type, relationship, tail entity, tail type), each backed by a verbatim evidence sentence from the chunk.

## Entity Types (use EXACTLY these names)
{render_entity_types()}

## Relationship Types (use EXACTLY these names)
{render_relation_types()}

## Extraction Rules
1. The filing company itself must always be typed ORG; every other company is COMP.
2. Normalize entity names: map every company reference to its stock ticker when known (e.g., Apple Inc. -> AAPL). Never output abstract references such as "we", "our", "it", or "the company" — resolve them to the concrete entity.
3. Keep entity names concise: at most 5 words, never whole sentences.
4. Extract only facts stated or strongly implied in the chunk — never invent.
5. `evidence` must be a verbatim sentence (or minimal span) copied from the chunk.
6. Tables are data too: extract metric/segment/geography facts from table rows.
7. If nothing can be extracted, return an empty triples array.

## Output Format
Return ONLY valid JSON (no markdown, no commentary):
{{
  "triples": [
    {{
      "head": "AAPL",
      "head_type": "ORG",
      "relation": "Introduces",
      "tail": "Vision Pro",
      "tail_type": "PRODUCT",
      "evidence": "In fiscal 2024 the Company introduced Vision Pro."
    }}
  ]
}}"""


def build_extraction_user_prompt(chunk_text: str, source_info: str) -> str:
    """抽取用户提示词：来源信息 + 待抽取 chunk。"""
    return f"""Filing context: {source_info}

Text chunk to analyze:
---
{chunk_text}
---

Extract all knowledge triples from this chunk. Return JSON only."""


def build_normalization_user_prompt(
    chunk_text: str,
    source_info: str,
    triples: list[dict[str, Any]],
) -> str:
    """multi_pass 第二遍规范化提示词（论文 4.3.2 的四项职责）。"""
    triples_json = json.dumps({"triples": triples}, ensure_ascii=False, indent=2)
    return f"""Filing context: {source_info}

Source chunk:
---
{chunk_text}
---

Candidate triples extracted in the first pass:
{triples_json}

This is a dedicated {NORMALIZE_MARKER}. Re-ingest the candidate triples together with the source chunk and produce a refined set:
1. Enforce canonical naming — substitute stock tickers for company references; resolve abstract references ("we", "the company") to the concrete entity.
2. Filter out triples whose entity or relationship types are not in the schema.
3. Merge duplicate or redundant entities and relationships.
4. Validate directionality and head/tail ordering for every relation; remove or correct invalid or ambiguous triples.

Keep the same JSON output format (top-level "triples" array). Return JSON only."""


def build_critic_system_prompt() -> str:
    """评审（Feedback LLM）系统提示词：逐三元组结构化反馈（论文 Box 4.1 格式）。"""
    return f"""You are the feedback (critic) LLM in a financial knowledge-graph reflection loop. Given a source chunk from an SEC 10-K filing and the current set of extracted triples, audit them and report issues.

The schema the triples must follow:

## Entity Types
{render_entity_types()}

## Relationship Types
{render_relation_types()}

Your duties:
1. Verify every entity label and relation assignment against the schema above.
2. Flag abstract entity references ("we", "our", "the company", "it") that must be normalized to a concrete entity such as the ticker.
3. Assess business relevance — flag low-value, vague, or contradictory triples.
4. Note clearly stated facts in the chunk that were MISSED.

Return ONLY valid JSON (no markdown) — a feedback array with one object per problem found:
{{
  "feedback": [
    {{
      "triple_number": "Triple 2",
      "triple": ["We", "ORG", "Impacted_By", "supply chain disruptions", "RISK_TYPE"],
      "issue": "Abstract reference 'We'; RISK_TYPE is not a valid preconfigured category",
      "suggestion": "Replace 'We' with the filer ticker; substitute RISK_TYPE with RISK_FACTOR"
    }}
  ]
}}
If a fact was missed, add a feedback item with "triple_number": "Missing" describing what to add.
If there are NO issues and nothing is missing, return {{"feedback": []}}."""


def build_critic_user_prompt(
    chunk_text: str,
    source_info: str,
    triples: list[dict[str, Any]],
) -> str:
    """评审用户提示词。"""
    triples_json = json.dumps({"triples": triples}, ensure_ascii=False, indent=2)
    return f"""Filing context: {source_info}

Source chunk:
---
{chunk_text}
---

Current triples to audit:
{triples_json}

Audit the triples and return the feedback JSON only."""


def build_corrector_user_prompt(
    chunk_text: str,
    source_info: str,
    triples: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
) -> str:
    """修正（Correction LLM）用户提示词：依逐条反馈修订或删除问题三元组。"""
    triples_json = json.dumps({"triples": triples}, ensure_ascii=False, indent=2)
    feedback_json = json.dumps({"feedback": feedback}, ensure_ascii=False, indent=2)
    return f"""Filing context: {source_info}

Source chunk:
---
{chunk_text}
---

Current triples:
{triples_json}

Critic feedback — {CORRECTOR_MARKER} below:
{feedback_json}

Produce the corrected, complete set of triples:
- Update or DROP each problematic triple according to its feedback item.
- ADD the facts marked as "Missing".
- Keep the same JSON output format (top-level "triples" array).
Return JSON only."""
