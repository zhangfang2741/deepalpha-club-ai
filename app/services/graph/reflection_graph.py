"""FinReflectKG 反思式图谱抽取（基于 LangGraph）。

参考论文 FinReflectKG（arXiv:2508.17906，*Agentic Construction and Evaluation of
Financial Knowledge Graphs*）实现"反思智能体"（reflection-agent）抽取范式。

论文核心思想：相比单次抽取（single-pass），引入 抽取→评审→修正 的反思闭环，
显著提升三元组的忠实度（faithfulness）、schema 合规性与完整性（comprehensiveness）。

本模块用 LangGraph `StateGraph` 编排该闭环，节点如下：

    extract  ── 抽取 LLM：从文本 chunk 产出初始三元组
       │
       ▼
    critique ── 评审 LLM + 确定性规则检查（CheckRules）：
       │        产出结构化问题清单与是否通过（approve）
       │
   ┌───┴───（有问题且未达最大轮次）
   │                                    通过 / 达到最大轮次
   ▼                                        │
    refine  ── 修正 LLM：依据反馈重抽/删改三元组 ──┐   │
       │                                          │   │
       └──────────────► 回到 critique ◄───────────┘   ▼
                                                      END

对外暴露 `extract_facts_with_reflection(...)`，签名与
`extractor.extract_facts_from_chunk(...)` 对齐，可在摄取流水线中平替。
"""

import json
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.core.logging import logger
from app.models.graph_entity import EntityType
from app.models.graph_fact import RelationType
from app.services.graph.extractor import (
    ExtractedFact,
    _build_user_prompt,
    _parse_llm_response,
    _SYSTEM_PROMPT,
    parse_extracted_facts,
)

# ──────────────────────────────────────────────────────────────────────────────
# CheckRules —— 确定性规则检查（对应论文 rule-based compliance policies）
# ──────────────────────────────────────────────────────────────────────────────

_VALID_ENTITY_TYPES = {t.value for t in EntityType}
_VALID_RELATION_TYPES = {r.value for r in RelationType}

# 每类关系合法的（头实体类型集合，尾实体类型集合）签名，与 graph_fact.RelationType 文档一致。
_RELATION_SIGNATURE: dict[str, tuple[set[str], set[str]]] = {
    "HAS_PRODUCT": ({"Company"}, {"Product"}),
    "SUPPLIED_BY": ({"Product", "Technology", "Resource"}, {"Company"}),
    "ENABLED_BY": ({"Concept", "Product"}, {"Technology", "Resource"}),
    "CONSTRAINED_BY": ({"Product", "Concept", "Resource"}, {"Resource", "Technology"}),
}

# 证据接地（grounding）判定阈值：证据词与原文词的重合比例下限。
# 取值偏宽松，避免因 LLM 轻度改写而误杀忠实三元组。
_GROUNDING_MIN_OVERLAP = 0.5


def _normalize_relation(raw: Any) -> str:
    """将关系字符串标准化为大写下划线形式（与枚举取值一致）。"""
    return str(raw or "").strip().upper().replace(" ", "_").replace("-", "_")


def _tokenize(text: str) -> set[str]:
    """粗粒度分词：小写、按非字母数字切分，用于证据接地重合度估算。"""
    return {tok for tok in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(tok) > 1}


def check_fact_rules(fact: dict[str, Any], chunk_text: str) -> list[str]:
    """对单条三元组执行确定性规则检查，返回违规信息列表（空列表表示合规）。

    覆盖论文四类 rule-based policies：
      1. Schema 合规：关系与实体类型合法，且头/尾类型组合符合关系签名。
      2. 证据忠实（faithfulness）：证据非空且能在原文中找到足够词重合（接地）。
      3. 实体良构：头尾实体名非空、非自环、长度合理。
      4. 置信度有效：confidence ∈ [0, 1]。
    """
    violations: list[str] = []

    src = fact.get("source_entity") or {}
    tgt = fact.get("target_entity") or {}
    src_name = str(src.get("name", "")).strip()
    tgt_name = str(tgt.get("name", "")).strip()
    src_type = str(src.get("type", "")).strip()
    tgt_type = str(tgt.get("type", "")).strip()
    relation = _normalize_relation(fact.get("relation"))
    evidence = str(fact.get("evidence", "")).strip()

    # 规则 3：实体良构
    if not src_name or not tgt_name:
        violations.append("实体名称为空（source/target 必须非空）")
    if src_name and tgt_name and src_name.lower() == tgt_name.lower():
        violations.append(f"自环三元组：'{src_name}' 指向自身，应删除")
    if len(src_name) > 120 or len(tgt_name) > 120:
        violations.append("实体名称过长，疑似把整句当作实体，应提炼为简洁实体名")

    # 规则 1：Schema 合规
    if relation not in _VALID_RELATION_TYPES:
        violations.append(
            f"非法关系类型 '{fact.get('relation')}'，仅允许：{sorted(_VALID_RELATION_TYPES)}"
        )
    if src_type and src_type not in _VALID_ENTITY_TYPES:
        violations.append(f"非法头实体类型 '{src_type}'，仅允许：{sorted(_VALID_ENTITY_TYPES)}")
    if tgt_type and tgt_type not in _VALID_ENTITY_TYPES:
        violations.append(f"非法尾实体类型 '{tgt_type}'，仅允许：{sorted(_VALID_ENTITY_TYPES)}")

    sig = _RELATION_SIGNATURE.get(relation)
    if sig and src_type and tgt_type:
        head_ok, tail_ok = sig
        if src_type not in head_ok or tgt_type not in tail_ok:
            violations.append(
                f"关系 {relation} 的类型组合不合法："
                f"应为 {sorted(head_ok)}→{sorted(tail_ok)}，实际 {src_type}→{tgt_type}"
            )

    # 规则 4：置信度有效
    try:
        conf = float(fact.get("confidence", 0.8))
        if not (0.0 <= conf <= 1.0):
            violations.append(f"置信度 {conf} 越界，应在 [0, 1]")
    except (TypeError, ValueError):
        violations.append("置信度非数值")

    # 规则 2：证据忠实与接地
    if not evidence:
        violations.append("缺少原文证据句（evidence 必填）")
    elif chunk_text:
        ev_tokens = _tokenize(evidence)
        chunk_tokens = _tokenize(chunk_text)
        if ev_tokens:
            overlap = len(ev_tokens & chunk_tokens) / len(ev_tokens)
            if overlap < _GROUNDING_MIN_OVERLAP:
                violations.append(
                    f"证据未接地：与原文词重合仅 {overlap:.0%}，疑似臆造，应改用原文原句"
                )

    return violations


def run_check_rules(facts: list[dict[str, Any]], chunk_text: str) -> dict[int, list[str]]:
    """对一批三元组批量执行 CheckRules，返回 {facts 下标: 违规信息列表}（仅含有违规者）。"""
    result: dict[int, list[str]] = {}
    for i, fact in enumerate(facts):
        v = check_fact_rules(fact, chunk_text)
        if v:
            result[i] = v
    return result


def compliance_score(facts: list[dict[str, Any]], chunk_text: str) -> float:
    """合规率：通过全部规则的三元组占比（论文 CheckRules compliance 指标的本地实现）。"""
    if not facts:
        return 1.0
    violated = len(run_check_rules(facts, chunk_text))
    return (len(facts) - violated) / len(facts)


def filter_compliant_facts(facts: list[dict[str, Any]], chunk_text: str) -> list[dict[str, Any]]:
    """丢弃仍然违反硬规则的三元组，仅保留完全合规者（终局兜底）。"""
    return [f for f in facts if not check_fact_rules(f, chunk_text)]


# ──────────────────────────────────────────────────────────────────────────────
# 反思图状态与提示词
# ──────────────────────────────────────────────────────────────────────────────


class ReflectionState(TypedDict):
    """反思抽取图的状态。"""

    chunk_text: str
    source_info: str
    facts: list[dict[str, Any]]  # 当前工作集（原始三元组 dict）
    critique: str  # 最近一次评审反馈（供修正节点使用）
    iteration: int  # 已完成的修正轮数
    max_iterations: int
    passed: bool  # 是否已通过评审（无问题）


_CRITIC_SYSTEM_PROMPT = """You are a meticulous financial knowledge-graph reviewer (critic).
Given a source text chunk and a list of extracted (head, relation, tail) triples, you audit the triples and report problems.

Check each triple for:
1. Faithfulness: is the fact actually stated or strongly implied in the text? Flag hallucinations.
2. Evidence grounding: does the `evidence` come from the source text (not invented)?
3. Schema correctness: relation ∈ {HAS_PRODUCT, SUPPLIED_BY, ENABLED_BY, CONSTRAINED_BY}; entity types ∈ {Company, Product, Technology, Concept, Resource}; and the head/tail types match the relation's direction.
4. Entity quality: canonical, concise entity names (not whole sentences); no self-loops.
5. Comprehensiveness: note clear value-chain facts in the text that were MISSED.

Return ONLY valid JSON (no markdown):
{
  "approve": true/false,
  "issues": ["specific problem with triple #i ...", ...],
  "missing": ["a clearly-stated fact that should be added ...", ...]
}
Set "approve" to true only if there are no issues and nothing important is missing."""


def _build_critic_prompt(state: ReflectionState, rule_violations: dict[int, list[str]]) -> str:
    """构造评审提示词：附上原文、当前三元组，以及确定性规则命中的违规。"""
    facts_json = json.dumps({"facts": state["facts"]}, ensure_ascii=False, indent=2)
    rule_lines = ""
    if rule_violations:
        parts = [f"  - triple #{i}: {'; '.join(v)}" for i, v in rule_violations.items()]
        rule_lines = "Automated rule checker already flagged:\n" + "\n".join(parts) + "\n\n"

    return f"""Source / focus: {state["source_info"]}

Source text chunk:
---
{state["chunk_text"]}
---

Extracted triples to review:
{facts_json}

{rule_lines}Audit the triples. Return JSON only."""


def _build_refine_prompt(state: ReflectionState) -> str:
    """构造修正提示词：原文 + 当前三元组 + 评审反馈，要求产出修正后的完整三元组集。"""
    facts_json = json.dumps({"facts": state["facts"]}, ensure_ascii=False, indent=2)
    return f"""Source / focus: {state["source_info"]}

Source text chunk:
---
{state["chunk_text"]}
---

Current triples:
{facts_json}

A reviewer found the following problems that you MUST fix:
{state["critique"]}

Produce a corrected, complete set of triples:
- Fix or DELETE triples that are unfaithful, mis-typed, self-looping, or ungrounded.
- ADD any clearly-stated value-chain facts that were missed.
- Keep the exact same JSON output format as the extraction schema (a top-level "facts" array).
Return JSON only."""


# ──────────────────────────────────────────────────────────────────────────────
# LangGraph 节点
# ──────────────────────────────────────────────────────────────────────────────


class ReflectionExtractor:
    """封装反思抽取图：持有 LLM 客户端与编译后的 LangGraph。

    一个 LLM 客户端在抽取/评审/修正三个角色间复用（论文允许同模型担任多角色）。
    """

    def __init__(self, llm_client: Any, max_iterations: int = 2):
        """初始化并编译反思图。

        Args:
            llm_client: LangChain BaseChatModel（需实现 ``ainvoke``）。
            max_iterations: 最大修正轮数（达到即停，防止无限反思）。
        """
        self.llm = llm_client
        self.max_iterations = max(0, max_iterations)
        self.graph = self._build_graph()

    async def _ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM 并返回纯文本响应。"""
        from langchain_core.messages import HumanMessage, SystemMessage

        response = await self.llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        return response.content if hasattr(response, "content") else str(response)

    async def _extract_node(self, state: ReflectionState) -> dict[str, Any]:
        """抽取节点：产出初始三元组。"""
        raw = await self._ainvoke_text(
            _SYSTEM_PROMPT, _build_user_prompt(state["chunk_text"], state["source_info"])
        )
        facts = _parse_llm_response(raw)
        logger.info("reflection_extract_done", fact_count=len(facts), source=state["source_info"][:80])
        return {"facts": facts, "iteration": 0, "passed": False, "critique": ""}

    async def _critique_node(self, state: ReflectionState) -> dict[str, Any]:
        """评审节点：确定性规则 + LLM 评审，合并出反馈与是否通过。"""
        facts = state["facts"]
        rule_violations = run_check_rules(facts, state["chunk_text"])

        # 无三元组时直接通过（无需评审）。
        if not facts:
            return {"passed": True, "critique": ""}

        approve = True
        issues: list[str] = []
        missing: list[str] = []
        try:
            raw = await self._ainvoke_text(_CRITIC_SYSTEM_PROMPT, _build_critic_prompt(state, rule_violations))
            verdict = _parse_critic_response(raw)
            approve = bool(verdict.get("approve", False))
            issues = [str(x) for x in verdict.get("issues", []) if str(x).strip()]
            missing = [str(x) for x in verdict.get("missing", []) if str(x).strip()]
        except Exception as e:
            # 评审失败不应中断抽取：退化为仅用确定性规则判定。
            logger.warning("reflection_critic_failed", error=str(e), source=state["source_info"][:80])

        # 汇总反馈：确定性规则违规 + LLM 评审问题 + 缺失项。
        feedback_parts: list[str] = []
        for i, v in rule_violations.items():
            feedback_parts.append(f"- Triple #{i}: {'; '.join(v)}")
        for issue in issues:
            feedback_parts.append(f"- {issue}")
        for m in missing:
            feedback_parts.append(f"- Missing fact to add: {m}")

        passed = approve and not rule_violations
        critique = "\n".join(feedback_parts)
        logger.info(
            "reflection_critique_done",
            passed=passed,
            rule_violations=len(rule_violations),
            llm_issues=len(issues),
            missing=len(missing),
            iteration=state["iteration"],
        )
        return {"passed": passed, "critique": critique}

    async def _refine_node(self, state: ReflectionState) -> dict[str, Any]:
        """修正节点：依据评审反馈重抽/删改三元组，轮次 +1。"""
        try:
            raw = await self._ainvoke_text(_SYSTEM_PROMPT, _build_refine_prompt(state))
            refined = _parse_llm_response(raw)
            # 修正后为空视为异常回退，保留原集合以免丢失全部结果。
            facts = refined if refined else state["facts"]
        except Exception as e:
            logger.warning("reflection_refine_failed", error=str(e), source=state["source_info"][:80])
            facts = state["facts"]

        iteration = state["iteration"] + 1
        logger.info("reflection_refine_done", fact_count=len(facts), iteration=iteration)
        return {"facts": facts, "iteration": iteration}

    def _route_after_critique(self, state: ReflectionState) -> str:
        """评审后路由：通过或达到最大轮次则结束，否则进入修正。"""
        if state["passed"] or state["iteration"] >= state["max_iterations"]:
            return END
        return "refine"

    def _build_graph(self):
        """构建并编译反思 StateGraph。"""
        builder = StateGraph(ReflectionState)
        builder.add_node("extract", self._extract_node)
        builder.add_node("critique", self._critique_node)
        builder.add_node("refine", self._refine_node)

        builder.add_edge(START, "extract")
        builder.add_edge("extract", "critique")
        builder.add_conditional_edges("critique", self._route_after_critique, {"refine": "refine", END: END})
        builder.add_edge("refine", "critique")

        return builder.compile(name="FinReflectKG Reflection Extractor")

    async def run(self, chunk_text: str, source_info: str) -> list[ExtractedFact]:
        """执行反思抽取，返回终局合规的 ExtractedFact 列表。"""
        initial: ReflectionState = {
            "chunk_text": chunk_text,
            "source_info": source_info,
            "facts": [],
            "critique": "",
            "iteration": 0,
            "max_iterations": self.max_iterations,
            "passed": False,
        }
        final_state = await self.graph.ainvoke(initial)
        raw_facts = final_state.get("facts", [])

        # 终局兜底：丢弃仍违反硬规则的三元组，再转为 ExtractedFact。
        clean = filter_compliant_facts(raw_facts, chunk_text)
        facts = parse_extracted_facts(clean)
        logger.info(
            "reflection_run_completed",
            source=source_info[:80],
            raw=len(raw_facts),
            compliant=len(clean),
            final=len(facts),
            iterations=final_state.get("iteration", 0),
        )
        return facts


def _parse_critic_response(response_text: str) -> dict[str, Any]:
    """解析评审 LLM 的 JSON 输出，鲁棒处理 markdown 包裹与非法 JSON。"""
    import re

    text = response_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    # 解析失败时保守处理：视为通过，避免无谓反思循环。
    logger.warning("critic_response_parse_failed", raw_text=text[:200])
    return {"approve": True, "issues": [], "missing": []}


async def extract_facts_with_reflection(
    chunk_text: str,
    source_info: str,
    llm_client: Any,
    max_iterations: int = 2,
) -> list[ExtractedFact]:
    """反思式抽取入口，签名与 ``extract_facts_from_chunk`` 对齐，可直接平替。

    Args:
        chunk_text: 800-1500 tokens 的文本块。
        source_info: 来源描述（如 "NVIDIA 10-K 2024, Risk Factors"）。
        llm_client: LangChain BaseChatModel 实例。
        max_iterations: 最大修正轮数，默认 2（论文推荐的效率/质量平衡点附近）。

    Returns:
        经反思闭环校验后的事实列表。
    """
    try:
        extractor = ReflectionExtractor(llm_client, max_iterations=max_iterations)
        return await extractor.run(chunk_text, source_info)
    except Exception as e:
        logger.exception("reflection_extraction_failed", source=source_info[:80], error=str(e))
        return []
