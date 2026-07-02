"""FinReflectKG 提示词 — schema-guided 抽取 / 增量补抽 / 评审 / 修正。

所有提示词将本体（ontology.py）动态渲染进上下文，
输出统一为论文 5 元组 + 原文证据的 JSON：

    {"triples": [{"head": ..., "head_type": ..., "relation": ...,
                  "tail": ..., "tail_type": ..., "evidence": ...}]}
"""

import json
from typing import Any

from app.services.graph.finreflect.ontology import render_entity_types, render_relation_types

# 修正提示词中的标记短语（测试与调试用，勿随意改动）
CORRECTOR_MARKER = "You MUST fix every problem listed"
MULTIPASS_MARKER = "ADDITIONAL triples"


def build_extraction_system_prompt() -> str:
    """schema-guided 抽取系统提示词（本体动态注入）。"""
    return f"""You are a financial knowledge-graph extraction agent. You read a chunk of a company's SEC 10-K annual report and extract knowledge triples in the form (head entity, head type, relationship, tail entity, tail type), each backed by a verbatim evidence sentence from the chunk.

## Entity Types (use EXACTLY these names)
{render_entity_types()}

## Relationship Types (use EXACTLY these names)
{render_relation_types()}

## Extraction Rules
1. The filing company itself must always be typed ORG; every other company is COMP.
2. Extract only facts stated or strongly implied in the chunk — never invent.
3. `evidence` must be a verbatim sentence (or minimal span) copied from the chunk.
4. Use concise canonical entity names, never whole sentences.
5. Tables are data too: extract metric/segment/geography facts from table rows.
6. If nothing can be extracted, return an empty triples array.

## Output Format
Return ONLY valid JSON (no markdown, no commentary):
{{
  "triples": [
    {{
      "head": "Apple",
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


def build_multipass_user_prompt(
    chunk_text: str,
    source_info: str,
    existing_triples: list[dict[str, Any]],
) -> str:
    """多轮抽取（multi-pass）提示词：仅要求补充遗漏的三元组。"""
    existing_json = json.dumps({"triples": existing_triples}, ensure_ascii=False, indent=2)
    return f"""Filing context: {source_info}

Text chunk to analyze:
---
{chunk_text}
---

Triples already extracted in previous passes:
{existing_json}

Extract ONLY {MULTIPASS_MARKER} that are present in the chunk but missing from the list above. Do not repeat existing triples. If nothing was missed, return an empty triples array. Return JSON only."""


def build_critic_system_prompt() -> str:
    """评审（Critic）系统提示词：审计三元组并产出结构化反馈。"""
    return f"""You are a meticulous financial knowledge-graph critic. Given a source chunk from an SEC 10-K filing and a list of extracted triples, audit them and report problems.

The schema the triples must follow:

## Entity Types
{render_entity_types()}

## Relationship Types
{render_relation_types()}

Audit each triple for:
1. Faithfulness — the fact is actually stated or strongly implied in the chunk (flag hallucinations).
2. Evidence grounding — `evidence` is copied from the chunk, not invented.
3. Schema conformance — head_type/tail_type and relation use exactly the names above, and the relation direction makes sense.
4. Entity quality — concise canonical names, ORG reserved for the filing company, no self-loops.
5. Comprehensiveness — clearly stated facts in the chunk that were MISSED.

Return ONLY valid JSON (no markdown):
{{
  "approve": true/false,
  "issues": ["problem with triple #i ...", ...],
  "missing": ["clearly-stated fact that should be added ...", ...]
}}
Set "approve" to true only when there are no issues and nothing important is missing."""


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

Extracted triples to audit:
{triples_json}

Audit the triples. Return JSON only."""


def build_corrector_user_prompt(
    chunk_text: str,
    source_info: str,
    triples: list[dict[str, Any]],
    critique: str,
) -> str:
    """修正（Corrector）用户提示词：依评审反馈产出修正后的完整三元组集。"""
    triples_json = json.dumps({"triples": triples}, ensure_ascii=False, indent=2)
    return f"""Filing context: {source_info}

Source chunk:
---
{chunk_text}
---

Current triples:
{triples_json}

Critic feedback — {CORRECTOR_MARKER} below:
{critique}

Produce the corrected, complete set of triples:
- Fix or DELETE unfaithful, mis-typed, self-looping, or ungrounded triples.
- ADD the clearly-stated facts the critic marked as missing.
- Keep the same JSON output format (top-level "triples" array).
Return JSON only."""
