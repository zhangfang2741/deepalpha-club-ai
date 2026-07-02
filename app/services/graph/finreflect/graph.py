"""FinReflectKG 抽取图 — LangGraph 编排的三种抽取模式（论文 4.3 节）。

- single_pass（式 1）：单一综合提示词一步抽取。
- multi_pass（式 2-3）：第一遍抽取候选三元组，第二遍将自身输出与原文
  一并重新输入，用专用规范化提示词精炼（规范命名/过滤越界类型/去重/校验方向）。
- reflection（式 4-6）：反思智能体 —— 抽取 LLM 产出初始三元组，
  Feedback LLM 产出逐三元组结构化反馈 F（Box 4.1 格式），
  Correction LLM 修订或删除问题三元组，循环直至 F = ∅ 或达最大步数 n_max。

图结构：

    START → extract ──┬─(single_pass)─────────────────────→ END
                      ├─(multi_pass)──→ normalize ─────────→ END
                      └─(reflection)──→ critique ─(F=∅/满)─→ END
                                          ▲   │(有反馈)
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
    build_normalization_user_prompt,
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
    feedback: list[dict[str, Any]]  # 最近一次评审反馈 F（Box 4.1 条目列表）
    iteration: int  # 已完成的反思步数 t
    max_iterations: int  # n_max


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


def parse_feedback_response(response_text: str) -> list[dict[str, Any]]:
    """解析 Feedback LLM 的结构化反馈（Box 4.1 格式）。

    返回反馈条目列表；空列表 = 无问题（停止条件 F = ∅）。
    解析失败时保守返回空列表，避免无谓反思循环。
    """
    text = _strip_code_fence(response_text)
    data: Any = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                pass
    if data is None:
        logger.warning("finreflect_feedback_parse_failed", raw_text=text[:200])
        return []

    if isinstance(data, dict):
        items = data.get("feedback", [])
    elif isinstance(data, list):
        items = data
    else:
        return []
    return [item for item in items if isinstance(item, dict)]


class FinReflectExtractor:
    """FinReflectKG 抽取器：持有 LLM 客户端与编译后的 LangGraph。

    论文允许同一模型分饰抽取/规范化/评审/修正角色，故复用单个客户端。
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
        """首轮抽取（式 1/2/4）：产出初始三元组集 T(1)。"""
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
        return {"triples": triples, "iteration": 0, "feedback": []}

    async def _normalize_node(self, state: FinReflectState) -> dict[str, Any]:
        """multi_pass 规范化遍（式 3）：模型重读原文与自身输出并精炼 T(2)。"""
        try:
            raw = await self._ainvoke_text(
                self._extraction_system,
                build_normalization_user_prompt(
                    state["chunk_text"], state["source_info"], state["triples"]
                ),
            )
            refined = parse_triples_response(raw)
            # 规范化结果为空视为异常回退，保留首遍集合以免丢失全部结果
            triples = refined if refined else state["triples"]
        except Exception as e:
            logger.warning("finreflect_normalize_failed", error=str(e))
            triples = state["triples"]

        logger.info("finreflect_normalize_done", triple_count=len(triples))
        return {"triples": triples}

    async def _critique_node(self, state: FinReflectState) -> dict[str, Any]:
        """Reflection 评审步（式 5）：Feedback LLM 产出逐三元组反馈 F(t)。"""
        if not state["triples"]:
            return {"feedback": []}

        try:
            raw = await self._ainvoke_text(
                self._critic_system,
                build_critic_user_prompt(state["chunk_text"], state["source_info"], state["triples"]),
            )
            feedback = parse_feedback_response(raw)
        except Exception as e:
            # 评审失败不应中断抽取：视为无反馈，带着当前集合结束
            logger.warning("finreflect_critic_failed", error=str(e))
            feedback = []

        logger.info(
            "finreflect_critique_done",
            feedback_count=len(feedback),
            iteration=state["iteration"],
        )
        return {"feedback": feedback}

    async def _refine_node(self, state: FinReflectState) -> dict[str, Any]:
        """Reflection 修正步（式 6）：Correction LLM 修订/删除问题三元组，t + 1。"""
        try:
            raw = await self._ainvoke_text(
                self._extraction_system,
                build_corrector_user_prompt(
                    state["chunk_text"], state["source_info"], state["triples"], state["feedback"]
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
        if state["mode"] == "multi_pass":
            return "normalize"
        return END

    def _route_after_critique(self, state: FinReflectState) -> str:
        """Reflection 停止条件：F = ∅（无反馈）或 t = n_max（达最大步数）。"""
        if not state["feedback"] or state["iteration"] >= state["max_iterations"]:
            return END
        return "refine"

    def _build_graph(self):
        """构建并编译抽取 StateGraph。"""
        builder = StateGraph(FinReflectState)
        builder.add_node("extract", self._extract_node)
        builder.add_node("normalize", self._normalize_node)
        builder.add_node("critique", self._critique_node)
        builder.add_node("refine", self._refine_node)

        builder.add_edge(START, "extract")
        builder.add_conditional_edges(
            "extract",
            self._route_after_extract,
            {"critique": "critique", "normalize": "normalize", END: END},
        )
        builder.add_edge("normalize", END)
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
    ) -> list[dict[str, Any]]:
        """执行抽取，返回带 CheckRules 合规标注的三元组列表。"""
        initial: FinReflectState = {
            "chunk_text": chunk_text,
            "source_info": source_info,
            "mode": mode,
            "triples": [],
            "feedback": [],
            "iteration": 0,
            "max_iterations": max(0, max_iterations),
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
        )
        return triples


async def extract_triples(
    chunk_text: str,
    source_info: str,
    llm_client: Any,
    mode: str = "reflection",
    max_iterations: int = 2,
) -> list[dict[str, Any]]:
    """FinReflectKG 抽取入口。

    Args:
        chunk_text: 待抽取的文本 chunk（表格感知切片产物）。
        source_info: 来源描述（如 "NVIDIA 10-K 2024"）。
        llm_client: LangChain BaseChatModel 实例。
        mode: single_pass | multi_pass | reflection。
        max_iterations: reflection 模式最大反思步数 n_max。

    Returns:
        论文 5 元组 dict 列表，每条带 ``evidence`` / ``compliant`` /
        ``violations`` / ``checkrules_score``。
    """
    if mode not in MODES:
        logger.warning("finreflect_unknown_mode", mode=mode)
        mode = "single_pass"
    try:
        extractor = FinReflectExtractor(llm_client)
        return await extractor.run(chunk_text, source_info, mode, max_iterations=max_iterations)
    except Exception as e:
        logger.exception("finreflect_extraction_failed", source=source_info[:80], error=str(e))
        return []
