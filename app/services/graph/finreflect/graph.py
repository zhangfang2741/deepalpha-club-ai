"""FinReflectKG 抽取图 — LangGraph 编排的三种抽取模式。

论文定义的三种模式（效率/质量权衡由用户选择）：
- single_pass：单次抽取，一个 chunk 一次 LLM 调用。
- multi_pass：固定多轮抽取，后续轮仅补抽遗漏三元组并去重合并。
- reflection：反思智能体 —— 抽取 LLM 产出初始三元组，评审 LLM（Critic）
  产出结构化反馈，修正 LLM（Corrector）依反馈修订，循环直至评审通过
  或达到最大轮次。

图结构：

    START → extract ──┬─(single)──────────────────────────→ END
                      ├─(multi)──→ extract_more ─┐
                      │               ▲          │(轮次未满)
                      │               └──────────┘ →(满)──→ END
                      └─(reflection)→ critique ─(通过/满)─→ END
                                        ▲   │(有问题)
                                        │   ▼
                                        └─ refine
"""

import json
import re
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.core.logging import logger
from app.services.graph.finreflect.checkrules import annotate_compliance, compliance_score
from app.services.graph.finreflect.prompts import (
    build_corrector_user_prompt,
    build_critic_system_prompt,
    build_critic_user_prompt,
    build_extraction_system_prompt,
    build_extraction_user_prompt,
    build_multipass_user_prompt,
)

# 支持的抽取模式
MODES = ("single_pass", "multi_pass", "reflection")

_TRIPLE_FIELDS = ("head", "head_type", "relation", "tail", "tail_type", "evidence")


class FinReflectState(TypedDict):
    """抽取图状态。"""

    chunk_text: str
    source_info: str
    mode: str  # single_pass | multi_pass | reflection
    triples: list[dict[str, Any]]  # 当前工作集（论文 5 元组 + evidence）
    critique: str  # 最近一次评审反馈（reflection 模式）
    passed: bool  # 评审是否通过（reflection 模式）
    iteration: int  # 已完成的修正轮数（reflection 模式）
    max_iterations: int
    passes: int  # 已完成的抽取轮数（multi_pass 模式）
    max_passes: int


def _strip_code_fence(text: str) -> str:
    """去除 markdown 代码块包裹。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    return re.sub(r"\s*```$", "", text, flags=re.MULTILINE)


def parse_triples_response(response_text: str) -> list[dict[str, Any]]:
    """解析 LLM 返回的三元组 JSON，仅保留字段齐整的条目。"""
    text = _strip_code_fence(response_text)
    raw: list[Any] = []
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            raw = data.get("triples", [])
        elif isinstance(data, list):
            raw = data
    except json.JSONDecodeError:
        match = re.search(r'\{.*"triples"\s*:\s*\[.*?\]\s*\}', text, re.DOTALL)
        if match:
            try:
                raw = json.loads(match.group()).get("triples", [])
            except json.JSONDecodeError:
                pass
        if not raw:
            logger.warning("finreflect_parse_failed", raw_text=text[:200])

    triples: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        triple = {field: str(item.get(field, "")).strip() for field in _TRIPLE_FIELDS}
        if triple["head"] and triple["tail"] and triple["relation"]:
            triples.append(triple)
    return triples


def parse_critic_response(response_text: str) -> dict[str, Any]:
    """解析评审 LLM 的 JSON 输出；解析失败保守视为通过，避免无谓循环。"""
    text = _strip_code_fence(response_text)
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
    logger.warning("finreflect_critic_parse_failed", raw_text=text[:200])
    return {"approve": True, "issues": [], "missing": []}


def _dedupe_key(triple: dict[str, Any]) -> tuple[str, str, str]:
    """去重键：(head, relation, tail) 忽略大小写。"""
    return (triple["head"].lower(), triple["relation"], triple["tail"].lower())


def merge_triples(
    existing: list[dict[str, Any]],
    additional: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """合并多轮抽取结果，按 (head, relation, tail) 去重。"""
    seen = {_dedupe_key(t) for t in existing}
    merged = list(existing)
    for triple in additional:
        key = _dedupe_key(triple)
        if key not in seen:
            seen.add(key)
            merged.append(triple)
    return merged


class FinReflectExtractor:
    """FinReflectKG 抽取器：持有 LLM 客户端与编译后的 LangGraph。

    论文允许同一模型分饰抽取/评审/修正三个角色，故复用单个客户端。
    """

    def __init__(self, llm_client: Any):
        """初始化并编译抽取图。"""
        self.llm = llm_client
        self._extraction_system = build_extraction_system_prompt()
        self._critic_system = build_critic_system_prompt()
        self.graph = self._build_graph()

    async def _ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM 并返回纯文本响应。"""
        from langchain_core.messages import HumanMessage, SystemMessage

        response = await self.llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        return response.content if hasattr(response, "content") else str(response)

    # ── 节点 ──────────────────────────────────────────────────────────────

    async def _extract_node(self, state: FinReflectState) -> dict[str, Any]:
        """首轮抽取：产出初始三元组。"""
        raw = await self._ainvoke_text(
            self._extraction_system,
            build_extraction_user_prompt(state["chunk_text"], state["source_info"]),
        )
        triples = parse_triples_response(raw)
        logger.info(
            "finreflect_extract_done",
            mode=state["mode"],
            triple_count=len(triples),
            source=state["source_info"][:80],
        )
        return {"triples": triples, "passes": 1, "iteration": 0, "passed": False, "critique": ""}

    async def _extract_more_node(self, state: FinReflectState) -> dict[str, Any]:
        """multi_pass 补抽轮：仅要求遗漏三元组，与既有集合去重合并。"""
        raw = await self._ainvoke_text(
            self._extraction_system,
            build_multipass_user_prompt(state["chunk_text"], state["source_info"], state["triples"]),
        )
        additional = parse_triples_response(raw)
        merged = merge_triples(state["triples"], additional)
        passes = state["passes"] + 1
        logger.info(
            "finreflect_multipass_done",
            new_triples=len(merged) - len(state["triples"]),
            total=len(merged),
            current_pass=passes,
        )
        return {"triples": merged, "passes": passes}

    async def _critique_node(self, state: FinReflectState) -> dict[str, Any]:
        """Reflection 评审轮：Critic LLM 审计三元组，产出结构化反馈。"""
        if not state["triples"]:
            return {"passed": True, "critique": ""}

        try:
            raw = await self._ainvoke_text(
                self._critic_system,
                build_critic_user_prompt(state["chunk_text"], state["source_info"], state["triples"]),
            )
            verdict = parse_critic_response(raw)
        except Exception as e:
            # 评审失败不应中断抽取：视为通过，带着当前集合结束
            logger.warning("finreflect_critic_failed", error=str(e))
            verdict = {"approve": True, "issues": [], "missing": []}

        approve = bool(verdict.get("approve", False))
        issues = [str(x) for x in verdict.get("issues", []) if str(x).strip()]
        missing = [str(x) for x in verdict.get("missing", []) if str(x).strip()]

        feedback = [f"- {issue}" for issue in issues]
        feedback += [f"- Missing fact to add: {m}" for m in missing]

        logger.info(
            "finreflect_critique_done",
            approve=approve,
            issues=len(issues),
            missing=len(missing),
            iteration=state["iteration"],
        )
        return {"passed": approve and not feedback, "critique": "\n".join(feedback)}

    async def _refine_node(self, state: FinReflectState) -> dict[str, Any]:
        """Reflection 修正轮：Corrector LLM 依反馈修订三元组，轮次 +1。"""
        try:
            raw = await self._ainvoke_text(
                self._extraction_system,
                build_corrector_user_prompt(
                    state["chunk_text"], state["source_info"], state["triples"], state["critique"]
                ),
            )
            refined = parse_triples_response(raw)
            # 修正后为空视为异常回退，保留原集合以免丢失全部结果
            triples = refined if refined else state["triples"]
        except Exception as e:
            logger.warning("finreflect_refine_failed", error=str(e))
            triples = state["triples"]

        iteration = state["iteration"] + 1
        logger.info("finreflect_refine_done", triple_count=len(triples), iteration=iteration)
        return {"triples": triples, "iteration": iteration}

    # ── 路由 ──────────────────────────────────────────────────────────────

    def _route_after_extract(self, state: FinReflectState) -> str:
        """首轮抽取后按模式分派。"""
        if state["mode"] == "reflection":
            return "critique"
        if state["mode"] == "multi_pass" and state["passes"] < state["max_passes"]:
            return "extract_more"
        return END

    def _route_after_extract_more(self, state: FinReflectState) -> str:
        """multi_pass 轮次控制。"""
        if state["passes"] < state["max_passes"]:
            return "extract_more"
        return END

    def _route_after_critique(self, state: FinReflectState) -> str:
        """Reflection 停止条件：评审通过或达到最大修正轮数。"""
        if state["passed"] or state["iteration"] >= state["max_iterations"]:
            return END
        return "refine"

    def _build_graph(self):
        """构建并编译抽取 StateGraph。"""
        builder = StateGraph(FinReflectState)
        builder.add_node("extract", self._extract_node)
        builder.add_node("extract_more", self._extract_more_node)
        builder.add_node("critique", self._critique_node)
        builder.add_node("refine", self._refine_node)

        builder.add_edge(START, "extract")
        builder.add_conditional_edges(
            "extract",
            self._route_after_extract,
            {"critique": "critique", "extract_more": "extract_more", END: END},
        )
        builder.add_conditional_edges(
            "extract_more",
            self._route_after_extract_more,
            {"extract_more": "extract_more", END: END},
        )
        builder.add_conditional_edges(
            "critique",
            self._route_after_critique,
            {"refine": "refine", END: END},
        )
        builder.add_edge("refine", "critique")

        return builder.compile(name="FinReflectKG Extractor")

    async def run(
        self,
        chunk_text: str,
        source_info: str,
        mode: str,
        max_iterations: int = 2,
        max_passes: int = 2,
    ) -> list[dict[str, Any]]:
        """执行抽取，返回带合规标注的三元组列表。"""
        initial: FinReflectState = {
            "chunk_text": chunk_text,
            "source_info": source_info,
            "mode": mode,
            "triples": [],
            "critique": "",
            "passed": False,
            "iteration": 0,
            "max_iterations": max(0, max_iterations),
            "passes": 0,
            "max_passes": max(1, max_passes),
        }
        final_state = await self.graph.ainvoke(initial)
        triples = annotate_compliance(final_state.get("triples", []), chunk_text)
        logger.info(
            "finreflect_run_completed",
            mode=mode,
            source=source_info[:80],
            triple_count=len(triples),
            compliance=round(compliance_score(triples, chunk_text), 3),
            iterations=final_state.get("iteration", 0),
            passes=final_state.get("passes", 0),
        )
        return triples


async def extract_triples(
    chunk_text: str,
    source_info: str,
    llm_client: Any,
    mode: str = "reflection",
    max_iterations: int = 2,
    max_passes: int = 2,
) -> list[dict[str, Any]]:
    """FinReflectKG 抽取入口。

    Args:
        chunk_text: 待抽取的文本 chunk（表格感知切片产物）。
        source_info: 来源描述（如 "NVIDIA 10-K 2024"）。
        llm_client: LangChain BaseChatModel 实例。
        mode: single_pass | multi_pass | reflection。
        max_iterations: reflection 模式最大修正轮数。
        max_passes: multi_pass 模式总抽取轮数。

    Returns:
        论文 5 元组 dict 列表，每条带 ``evidence`` / ``compliant`` / ``violations``。
    """
    if mode not in MODES:
        logger.warning("finreflect_unknown_mode", mode=mode)
        mode = "single_pass"
    try:
        extractor = FinReflectExtractor(llm_client)
        return await extractor.run(
            chunk_text, source_info, mode, max_iterations=max_iterations, max_passes=max_passes
        )
    except Exception as e:
        logger.exception("finreflect_extraction_failed", source=source_info[:80], error=str(e))
        return []
