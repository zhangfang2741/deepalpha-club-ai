"""TradingAgentsEngine —— 包装 tradingagents 0.7.0 的真实多 Agent 图。

设计要点（plan §3 + 探针结论）：
  - 不复用 `ta.graph`：上游 setup_graph() 总是 compile() 一刀切，没传
    checkpointer / interrupt_before 的机会。本引擎自建一份 GraphSetup 实例，
    复刻其节点/边构造逻辑并自己 compile，把运行时控制权收回来。
  - LLM 注入：构造 ta 拿到 memories/materialize 工具节点，然后丢弃 ta，
    用我们自己的 GraphSetup 拿注入的 LLM 重新拼图。两边 LLM 实例一致即可。
  - 双模式流：astream(stream_mode=["messages", "updates"]) 把 LangGraph 的
    token + state chunk 喂给 StreamTranslator，引擎不直接解 chunk。
  - HITL 在引擎主循环里实现：节点边界重入 pump 之前等 pause、drain_notes 注入；
    interrupt_before 也保留，给未来「前端在节点边界硬暂停」留余地。
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from tradingagents import TradingAgentsConfig, TradingAgentsGraph
from tradingagents.agents import (
    AgentState,
    create_aggressive_debator,
    create_bear_researcher,
    create_bull_researcher,
    create_conservative_debator,
    create_fundamentals_analyst,
    create_market_analyst,
    create_msg_delete,
    create_neutral_debator,
    create_news_analyst,
    create_research_manager,
    create_risk_manager,
    create_situation_summariser,
    create_social_media_analyst,
    create_trader,
)
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import (
    GraphSetup,
    MemoryComponents,
    SUPPORTED_ANALYSTS,
)

from app.core.config import settings
from app.core.logging import logger
from app.schemas.trading_desk import (
    ConsensusData,
    EngineCapabilities,
    EngineDescriptor,
    EventType,
    HumanNoteData,
    Polarity,
    SignalData,
    TradingDeskEvent,
    VerdictData,
)
from app.services.llm.registry import llm_registry
from app.services.trading_desk.engine_base import RunContext
from app.services.trading_desk.engines import stage_map
from app.services.trading_desk.engines.stream_translator import StreamTranslator
from app.services.trading_desk.signal_extract import extract_signal, quick_llm

# 注入目标：交易员前/后的人工意见追加到这两个字段（计划一探针已验证）。
_PRE_TRADER_FIELD = "news_report"
_POST_TRADER_FIELD = "trader_investment_plan"

# 引擎名（用于 describe / EngineDescriptor.engine）。
_ENGINE_PREFIX = "tradingagents"


def _consensus_from_signals(signals: list[tuple[Polarity, int]]) -> ConsensusData:
    """按方向计数并给出倾向描述。mock.py 同款口径，让事件协议两边一致。"""
    bull = sum(1 for d, _ in signals if d == "bull")
    bear = sum(1 for d, _ in signals if d == "bear")
    neutral = sum(1 for d, _ in signals if d == "neutral")
    total = len(signals) or 1

    if bull > bear:
        lean = "明显偏多" if bull >= total * 0.6 else "略偏多"
    elif bear > bull:
        lean = "偏空"
    else:
        lean = "分歧"

    return ConsensusData(bull=bull, neutral=neutral, bear=bear, lean=lean)


class TradingAgentsEngine:
    """tradingagents 引擎。生产路径用平台 LLM；测试注入 llm_override。"""

    name = _ENGINE_PREFIX

    def __init__(
        self,
        *,
        checkpointer: object | None = None,
        results_dir: Path | None = None,
        llm_override: object | None = None,
        extractor_llm: object | None = None,
        selected_analysts: list[str] | None = None,
    ) -> None:
        """初始化引擎。

        Args:
            checkpointer: LangGraph checkpointer（生产用 AsyncPostgresSaver，
                测试用 InMemorySaver）；None 走禁用路径（HITL 也将失效）。
            results_dir: tradingagents 的结果目录与 data_cache 都在这里。
            llm_override: 测试用 LLM（跳过 llm_registry）。
            extractor_llm: 测试替换 signal_extract 的 quick LLM。
            selected_analysts: TradingAgents 启用的分析师集合；空走默认全集。
        """
        self._checkpointer = checkpointer
        self._results_dir = results_dir
        self._llm_override = llm_override
        self._extractor_llm = extractor_llm
        self._selected_analysts = selected_analysts or list(SUPPORTED_ANALYSTS)

    def describe(self) -> EngineDescriptor:
        """自报拓扑与能力，按 stage_map 折叠去重。"""
        import importlib.metadata as md

        stages = []
        seen: set[str] = set()
        for node in stage_map.AGENT_NODES:
            d = stage_map.stage_of(node)
            if d and d.id not in seen:
                seen.add(d.id)
                stages.append(d)
        return EngineDescriptor(
            engine=f"{_ENGINE_PREFIX}/{md.version('tradingagents')}",
            capabilities=EngineCapabilities(supports_pause=True, supports_inject=True),
            stages=stages,
        )

    async def astream(self, ctx: RunContext) -> AsyncIterator[TradingDeskEvent]:
        """产出事件异步流；run.started/run.finished 由 runner 包裹。"""
        # TradingAgents 上游 prompts 模块按 BCP 47 简写（"zh-CN"）拼
        # "Please respond in {language}"，但 Claude/GPT 把 BCP 47 当字面
        # 字符串而非 locale 名——LLM 实际仍输出英文。在引擎启动时把
        # prompts._language_instruction 替换为返回完整 locale 名 + 中文
        # locale 名，并附明确指令，强制 LLM 用中文输出。BUY/SELL/HOLD
        # 按 tradingagents 上游约定保持英文，避免下游 signal 抽取 regex
        # 失配。
        from tradingagents.agents import prompts as _ta_prompts

        _LANGUAGE_NAMES: dict[str, tuple[str, str]] = {
            "zh-CN": ("Simplified Chinese", "简体中文"),
            "zh-TW": ("Traditional Chinese", "繁體中文"),
            "en-US": ("English (United States)", ""),
            "ja-JP": ("Japanese", "日本語"),
            "ko-KR": ("Korean", "한국어"),
            "de-DE": ("German", "Deutsch"),
        }

        def _localized_language_instruction() -> str:
            tag = settings.TRADING_DESK_RESPONSE_LANGUAGE.strip() or "zh-CN"
            en_name, native_name = _LANGUAGE_NAMES.get(tag, ("English (United States)", ""))
            if native_name:
                return (
                    f"\n\n请用 {native_name}（{en_name}，BCP 47: {tag}）回复正文。"
                    "专有名词、指标符号、信号标签 BUY/SELL/HOLD 保持英文——"
                    "下游工具用 regex 抽取这些 token。"
                )
            return (
                f"\n\nPlease respond in {en_name} ({tag}). "
                "Keep `BUY`, `SELL`, or `HOLD` in English for downstream tooling."
            )

        _ta_prompts._language_instruction = _localized_language_instruction  # type: ignore[attr-defined]

        results_dir = self._results_dir or Path(tempfile.gettempdir()) / "trading_desk"
        config = TradingAgentsConfig(
            results_dir=results_dir,
            llm_provider="openai",  # 注入 LLM 后这里只是元数据日志
            deep_think_llm=settings.TRADING_DESK_DEEP_MODEL or "platform-default",
            quick_think_llm=settings.TRADING_DESK_QUICK_MODEL or "platform-default",
            response_language=settings.TRADING_DESK_RESPONSE_LANGUAGE or "zh-CN",  # type: ignore[arg-type]
            max_debate_rounds=settings.TRADING_DESK_MAX_DEBATE_ROUNDS,
            max_risk_discuss_rounds=settings.TRADING_DESK_MAX_RISK_ROUNDS,
            max_recur_limit=100,
        )

        # 临时 ta 实例用来 materialize memories / tool_nodes，然后丢弃；
        # 实际图用我们自己 GraphSetup 装的注入 LLM 重新拼。
        ta = TradingAgentsGraph(config=config)
        for attr in ("bull_memory", "bear_memory", "trader_memory", "invest_judge_memory", "risk_manager_memory"):
            _ = getattr(ta, attr)
        memories = MemoryComponents(
            bull=ta.bull_memory, bear=ta.bear_memory, trader=ta.trader_memory,
            invest_judge=ta.invest_judge_memory, risk_manager=ta.risk_manager_memory,
        )
        tool_nodes = ta.tool_nodes

        if self._llm_override is not None:
            deep = self._llm_override
            quick = self._llm_override
        else:
            deep, _ = llm_registry.get_or_default(settings.TRADING_DESK_DEEP_MODEL or None)
            quick, _ = llm_registry.get_or_default(settings.TRADING_DESK_QUICK_MODEL or None)

            # Anthropic extended thinking：给 LLM 加 thinking 参数，让 agent 把
            # 推理链作为独立 content block 流出来。仅对 claude-3-7+ / 4.x 生效；
            # 非 Anthropic 模型的构造参数里没有 thinking，model_copy(update=...)
            # 会沿用其他 init 字段，对 gpt / gemini 无副作用。
            if settings.TRADING_DESK_ENABLE_THINKING:
                deep = deep.model_copy(
                    update={
                        "thinking": {
                            "type": "enabled",
                            "budget_tokens": settings.TRADING_DESK_THINK_BUDGET,
                        },
                    },
                )
                quick = quick.model_copy(
                    update={
                        "thinking": {
                            "type": "enabled",
                            "budget_tokens": settings.TRADING_DESK_THINK_BUDGET,
                        },
                    },
                )

        graph_setup = GraphSetup(
            quick_thinking_llm=quick,  # type: ignore[arg-type]
            deep_thinking_llm=deep,  # type: ignore[arg-type]
            tool_nodes=tool_nodes,
            memories=memories,
            conditional_logic=ConditionalLogic(
                max_debate_rounds=config.max_debate_rounds,
                max_risk_discuss_rounds=config.max_risk_discuss_rounds,
            ),
        )
        workflow = self._build_uncompiled_workflow(graph_setup, self._selected_analysts)
        compiled: CompiledStateGraph = workflow.compile(
            checkpointer=self._checkpointer,  # type: ignore[arg-type]
            interrupt_before=list(stage_map.AGENT_NODES),
        )
        # 暴露给同进程测试快速校验终态；生产路径不需要
        self._compiled = compiled

        cfg: dict[str, Any] = {"configurable": {"thread_id": ctx.run_id}, "recursion_limit": 100}
        init = ta.propagator.create_initial_state(ctx.ticker, ctx.trade_date)

        translator = StreamTranslator(run_id=ctx.run_id)
        extractor = self._extractor_llm or quick_llm()
        signals: list[tuple[Polarity, int]] = []
        run_input: dict[str, Any] | None = init
        run_cfg: dict[str, Any] = dict(cfg)
        stream_mode: list[str] = ["messages", "updates"]

        while True:
            async for event in self._pump(
                compiled, run_input, run_cfg, stream_mode, translator, extractor, signals, ctx,
            ):
                yield event

            if await ctx.control.is_cancelled():
                return

            state = await compiled.aget_state(run_cfg)
            if not state.next:  # 图跑完了
                return

            await self._wait_if_paused(ctx)
            if await ctx.control.is_cancelled():
                return

            async for event in self._inject_notes(compiled, run_cfg, state, ctx):
                yield event
            run_input = None  # 恢复执行用 None，靠 checkpointer 续状态

    # ── 工作流构建 ─────────────────────────────────

    @staticmethod
    def _build_uncompiled_workflow(graph_setup: Any, selected_analysts: list[str]) -> StateGraph:
        """复刻 GraphSetup.setup_graph() 的节点/边构造，停在 compile() 之前。

        必传 kwargs：checkpointer 与 interrupt_before。本函数拿到的就是
        还会再 compile 的 StateGraph 实例。
        """
        analyst_creators = {
            "market": create_market_analyst,
            "social": create_social_media_analyst,
            "news": create_news_analyst,
            "fundamentals": create_fundamentals_analyst,
        }
        analyst_nodes: dict[str, Any] = {}
        delete_nodes: dict[str, Any] = {}

        for analyst_type in selected_analysts:
            if analyst_type in analyst_creators:
                analyst_nodes[analyst_type] = analyst_creators[analyst_type](
                    graph_setup.quick_thinking_llm
                )
                delete_nodes[analyst_type] = create_msg_delete()

        workflow = StateGraph(AgentState)

        for analyst_type, node in analyst_nodes.items():
            cap = analyst_type.capitalize()
            workflow.add_node(f"{cap} Analyst", node)
            workflow.add_node(f"Msg Clear {cap}", delete_nodes[analyst_type])
            workflow.add_node(f"tools_{analyst_type}", graph_setup.tool_nodes[analyst_type])

        workflow.add_node("Situation Summariser", create_situation_summariser(graph_setup.quick_thinking_llm))
        workflow.add_node("Bull Researcher", create_bull_researcher(graph_setup.quick_thinking_llm, graph_setup.memories.bull))
        workflow.add_node("Bear Researcher", create_bear_researcher(graph_setup.quick_thinking_llm, graph_setup.memories.bear))
        workflow.add_node("Research Manager", create_research_manager(graph_setup.deep_thinking_llm, graph_setup.memories.invest_judge))
        workflow.add_node("Trader", create_trader(graph_setup.quick_thinking_llm, graph_setup.memories.trader))
        workflow.add_node("Aggressive Analyst", create_aggressive_debator(graph_setup.quick_thinking_llm))
        workflow.add_node("Neutral Analyst", create_neutral_debator(graph_setup.quick_thinking_llm))
        workflow.add_node("Conservative Analyst", create_conservative_debator(graph_setup.quick_thinking_llm))
        workflow.add_node("Risk Judge", create_risk_manager(graph_setup.deep_thinking_llm, graph_setup.memories.risk_manager))

        first = selected_analysts[0].capitalize()
        workflow.add_edge(START, f"{first} Analyst")

        # 分析师串行
        for i, atype in enumerate(selected_analysts):
            cur = f"{atype.capitalize()} Analyst"
            cur_tools = f"tools_{atype}"
            cur_clear = f"Msg Clear {atype.capitalize()}"
            workflow.add_conditional_edges(
                cur,
                getattr(graph_setup.conditional_logic, f"should_continue_{atype}"),
                [cur_tools, cur_clear],
            )
            workflow.add_edge(cur_tools, cur)
            if i < len(selected_analysts) - 1:
                nxt = f"{selected_analysts[i + 1].capitalize()} Analyst"
                workflow.add_edge(cur_clear, nxt)
            else:
                workflow.add_edge(cur_clear, "Situation Summariser")

        cl = graph_setup.conditional_logic
        workflow.add_edge("Situation Summariser", "Bull Researcher")
        workflow.add_conditional_edges(
            "Bull Researcher", cl.should_continue_debate,
            {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_conditional_edges(
            "Bear Researcher", cl.should_continue_debate,
            {"Bull Researcher": "Bull Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        workflow.add_conditional_edges(
            "Aggressive Analyst", cl.should_continue_risk_analysis,
            {"Conservative Analyst": "Conservative Analyst", "Risk Judge": "Risk Judge"},
        )
        workflow.add_conditional_edges(
            "Conservative Analyst", cl.should_continue_risk_analysis,
            {"Neutral Analyst": "Neutral Analyst", "Risk Judge": "Risk Judge"},
        )
        workflow.add_conditional_edges(
            "Neutral Analyst", cl.should_continue_risk_analysis,
            {"Aggressive Analyst": "Aggressive Analyst", "Risk Judge": "Risk Judge"},
        )
        workflow.add_edge("Risk Judge", END)
        return workflow

    # ── 主循环内 helper ─────────────────────────────

    async def _pump(
        self,
        compiled: CompiledStateGraph,
        run_input: dict[str, Any] | None,
        cfg: dict[str, Any],
        stream_mode: list[str],
        translator: StreamTranslator,
        extractor: Any,
        signals: list[tuple[Polarity, int]],
        ctx: RunContext,
    ) -> AsyncIterator[TradingDeskEvent]:
        """跑一段图：吃 chunk、流翻译、抽信号、产 verdict。"""
        async for chunk in compiled.astream(run_input, cfg, stream_mode=stream_mode):  # type: ignore[arg-type]
            if await ctx.control.is_cancelled():
                return

            for event in translator.feed(chunk):
                yield event

            # 等到一批 chunk 之后批量抽信号（避免逐 chunk 触发 LLM）
            for stage_id, stage_name, report in translator.pending_reports():
                direction, conf = await extract_signal(
                    extractor, stage_name=stage_name, report=report,
                )
                signals.append((direction, conf))
                yield TradingDeskEvent.of(
                    ctx.run_id, EventType.AGENT_SIGNAL, SignalData(
                        stage_id=stage_id, name=stage_name,
                        dir=direction, conf=conf, extracted=True,
                    ),
                )
                yield TradingDeskEvent.of(
                    ctx.run_id, EventType.CONSENSUS_UPDATE, _consensus_from_signals(signals),
                )

            verdict_text = translator.verdict_text()
            if verdict_text:
                for ev in translator.flush_stage():
                    yield ev
                yield self._build_verdict(ctx, compiled, verdict_text)
        return

    def _build_verdict(
        self, ctx: RunContext, ta_or_compiled: Any, text: str,
    ) -> TradingDeskEvent:
        """用 tradingagents 的 process_signal 解析裁决文本。

        `ta_or_compiled` 形参只是占位对齐 extract 接口签名；实际解析走全局
        SignalProcessor 实例（无外部 LLM 依赖，纯正则 + JSON）。
        """
        from tradingagents.graph.signal_processing import SignalProcessor

        rec = SignalProcessor().process_signal(text)
        return TradingDeskEvent.of(ctx.run_id, EventType.VERDICT, VerdictData(
            signal=rec.signal,
            confidence=rec.confidence,
            size_fraction=rec.size_fraction,
            entry_reference_price=rec.entry_reference_price,
            target_price=rec.target_price,
            stop_loss=rec.stop_loss,
            currency=rec.currency,
            time_horizon_days=rec.time_horizon_days,
            rationale=rec.rationale,
            warning_message=rec.warning_message,
        ))

    async def _wait_if_paused(self, ctx: RunContext) -> None:
        """节点边界响应暂停：放空等待直到解除，期间监听取消。"""
        while await ctx.control.is_paused():
            if await ctx.control.is_cancelled():
                return
            await asyncio.sleep(0.5)

    async def _inject_notes(
        self,
        compiled: CompiledStateGraph,
        cfg: dict[str, Any],
        state: Any,
        ctx: RunContext,
    ) -> AsyncIterator[TradingDeskEvent]:
        """把积压意见嫁接到引擎 state。

        注入窗口（spec §5.3）：
          - ``news_report`` 必须等 News Analyst 跑过以后再写：再早会被该
            节点自身的 report 覆盖。
          - ``trader_investment_plan`` 必须等 Trader 跑过以后再写：再早
            同理。
          注入窗口不到的 note 留到下一轮再判，drained 但不写也不发事件——
          避免用户以为写了其实被覆盖的迷惑。
        """
        order = list(stage_map.AGENT_NODES)
        news_idx = order.index("News Analyst")
        trader_idx = order.index("Trader")

        notes = await ctx.control.drain_notes()
        if not notes:
            return

        next_node = state.next[0] if state.next else None
        next_idx = order.index(next_node) if next_node in order else trader_idx + 1

        # 决定目标字段。窗口不到时 notes 留到下轮再判（不发事件，避免误导）。
        field: str | None = None
        if next_idx > trader_idx:
            field = _POST_TRADER_FIELD
        elif next_idx > news_idx:
            field = _PRE_TRADER_FIELD

        if field is None:
            logger.info(
                "trading_desk_inject_deferred",
                run_id=ctx.run_id,
                count=len(notes),
                at_node=next_node,
            )
            return

        for note in notes:
            values = state.values if isinstance(state.values, dict) else dict(vars(state.values))
            current = str(values.get(field, "") or "")
            await compiled.aupdate_state(cfg, {field: f"{current}\n\n---\n【人工补充意见】{note}"})  # type: ignore[arg-type]

            yield TradingDeskEvent.of(
                ctx.run_id, EventType.HUMAN_NOTE, HumanNoteData(text=note, injected_into=field),
            )
            state = await compiled.aget_state(cfg)  # 连续注入要重取
