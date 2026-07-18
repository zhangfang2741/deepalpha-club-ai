"""LangGraph Deep Agent 封装：基于 deepagents 构建具备规划/子智能体/虚拟文件系统能力的投研 Agent。

本模块用 ``deepagents.create_deep_agent`` 替换了原先手写的 ``_chat`` ↔ ``_tool_call``
两节点循环，同时保留对外的公共方法（get_response / get_stream_response / get_chat_history /
clear_chat_history），并新增面向 assistant-ui ``useLangGraphRuntime`` 的
``get_langgraph_stream`` / ``get_langgraph_history``。

- 复用现有投研工具（app.core.langgraph.tools）。
- 复用 Postgres AsyncPostgresSaver 做检查点持久化。
- 复用 mem0 长期记忆：每轮检索后通过 dynamic_prompt 中间件注入 system prompt，
  不写入持久化状态。
"""

import asyncio
import json
from typing import (
    Any,
    AsyncGenerator,
    Optional,
    TypedDict,
    cast,
)
from urllib.parse import quote_plus

from langchain.agents.middleware import dynamic_prompt
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    convert_to_openai_messages,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.errors import GraphInterrupt
from langchain_core.runnables.config import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import (
    Command,
    StateSnapshot,
)
from psycopg import (
    AsyncConnection,
    sql,
)
from psycopg.rows import (
    DictRow,
    dict_row,
)
from psycopg_pool import AsyncConnectionPool

from deepagents import create_deep_agent

from app.core.config import (
    Environment,
    settings,
)
from app.core.langgraph.tools import tools
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.core.observability import langfuse_callback_handler
from app.core.prompts import (
    build_dynamic_context,
    load_deep_agent_prompt,
)
from app.schemas import Message
from app.services.llm.registry import llm_registry
from app.services.memory import memory_service
from app.utils import (
    dump_messages,
    extract_text_content,
)

PostgresConnPool = AsyncConnectionPool[AsyncConnection[DictRow]]


class AgentContext(TypedDict, total=False):
    """Deep Agent 每轮运行时上下文（不进入持久化状态）。

    Attributes:
        dynamic_context: 当前轮注入的动态文本（用户信息 + 长期记忆 + 当前时间）。
    """

    dynamic_context: str


@dynamic_prompt
def _inject_dynamic_context(request: Any) -> str:
    """在 deepagents 组合好的 system prompt 之后追加每轮动态上下文。

    读取 ``request.system_prompt``（已包含 deepagents 规划/文件系统/子智能体指令
    以及我们的静态投研指令），再追加运行时上下文中的动态内容。
    """
    base = request.system_prompt or ""
    ctx = request.runtime.context or {}
    dynamic = ctx.get("dynamic_context", "") if isinstance(ctx, dict) else ""
    if dynamic:
        return f"{base}\n\n{dynamic}"
    return base


def _serialize_message(message: BaseMessage) -> dict:
    """将 LangChain 消息序列化为 assistant-ui react-langgraph 期望的 dict 形态。"""
    data = message.model_dump()
    # model_dump 对 chunk 返回 type='AIMessageChunk'，对完整消息返回 human/ai/tool/system
    return data


class LangGraphAgent:
    """管理基于 deepagents 的 Deep Agent 工作流及其与 LLM 的交互。"""

    def __init__(self):
        """初始化 Deep Agent 管理器。"""
        self.tools = tools
        self._connection_pool: Optional[PostgresConnPool] = None
        # 使用 Any：create_deep_agent 返回带 AgentContext 的泛型图，
        # 其 ContextT 不变型与 Optional[CompiledStateGraph] 默认 None 不兼容。
        self._graph: Any = None
        logger.info(
            "deep_agent_initialized",
            model=settings.DEFAULT_LLM_MODEL,
            environment=settings.ENVIRONMENT.value,
            tool_count=len(self.tools),
        )

    async def _get_connection_pool(self) -> Optional[PostgresConnPool]:
        """获取 PostgreSQL 连接池（按环境配置），失败时在生产环境降级返回 None。"""
        if self._connection_pool is None:
            try:
                max_size = settings.POSTGRES_POOL_SIZE
                _ssl_mode = "require" if settings.POSTGRES_SSL else "disable"
                connection_url = (
                    "postgresql://"
                    f"{quote_plus(settings.POSTGRES_USER)}:{quote_plus(settings.POSTGRES_PASSWORD)}"
                    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
                )
                self._connection_pool = AsyncConnectionPool(
                    connection_url,
                    open=False,
                    max_size=max_size,
                    kwargs={
                        "autocommit": True,
                        "connect_timeout": 5,
                        "prepare_threshold": None,
                        "row_factory": dict_row,
                        "sslmode": _ssl_mode,
                    },
                )
                await self._connection_pool.open()
                logger.info("connection_pool_created", max_size=max_size, environment=settings.ENVIRONMENT.value)
            except Exception as e:
                logger.error("connection_pool_creation_failed", error=str(e), environment=settings.ENVIRONMENT.value)
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    logger.warning("continuing_without_connection_pool", environment=settings.ENVIRONMENT.value)
                    return None
                raise e
        return self._connection_pool

    async def create_graph(self) -> Any:
        """构建并编译 Deep Agent 图。

        Returns:
            Optional[CompiledStateGraph]: 编译好的图；初始化失败时（仅生产环境）返回 None。
        """
        if self._graph is None:
            try:
                connection_pool = await self._get_connection_pool()
                if connection_pool:
                    checkpointer = AsyncPostgresSaver(connection_pool)
                    await checkpointer.setup()
                else:
                    checkpointer = None
                    if settings.ENVIRONMENT != Environment.PRODUCTION:
                        raise Exception("Connection pool initialization failed")

                self._graph = create_deep_agent(
                    model=llm_registry.get_default(),
                    tools=self.tools,
                    system_prompt=load_deep_agent_prompt(),
                    middleware=[_inject_dynamic_context],
                    context_schema=AgentContext,
                    checkpointer=checkpointer,
                    name=f"{settings.PROJECT_NAME} Deep Agent ({settings.ENVIRONMENT.value})",
                )

                logger.info(
                    "deep_agent_graph_created",
                    environment=settings.ENVIRONMENT.value,
                    has_checkpointer=checkpointer is not None,
                )
            except Exception as e:
                logger.error("graph_creation_failed", error=str(e), environment=settings.ENVIRONMENT.value)
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    logger.warning("continuing_without_graph")
                    return None
                raise e

        return self._graph

    async def _get_graph(self) -> Any:
        """返回已编译的图，首次访问时创建。"""
        if self._graph is None:
            self._graph = await self.create_graph()
        if self._graph is None:
            raise RuntimeError("graph initialization failed")
        return self._graph

    def _build_config(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> RunnableConfig:
        """构建 LangGraph 运行配置（含 thread_id、回调、metadata）。"""
        callbacks: list[BaseCallbackHandler] = (
            [langfuse_callback_handler] if settings.LANGFUSE_TRACING_ENABLED else []
        )
        return {
            "configurable": {"thread_id": session_id},
            "callbacks": callbacks,
            "metadata": {
                "user_id": user_id,
                "username": username,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": settings.DEBUG,
            },
        }

    async def _resolve_input(
        self,
        graph: CompiledStateGraph,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str],
        username: Optional[str],
        resume_value: Optional[str] = None,
    ) -> tuple[Any, RunnableConfig, AgentContext]:
        """决定本轮的图输入（正常输入 or 中断恢复），并构建运行配置与运行时上下文。"""
        # 检查是否处于中断态 + 并发检索长期记忆
        last_content = messages[-1].content if messages else ""
        state, relevant_memory = await asyncio.gather(
            graph.aget_state({"configurable": {"thread_id": session_id}}),
            memory_service.search(user_id, last_content),
        )
        dynamic_context = build_dynamic_context(
            username=username, long_term_memory=relevant_memory or ""
        )
        config = self._build_config(session_id, user_id, username)
        context: AgentContext = {"dynamic_context": dynamic_context}

        if state.next:
            # 图处于中断态：用最新用户输入作为 resume 值恢复
            resume = resume_value if resume_value is not None else last_content
            logger.info("resuming_interrupted_deep_agent", session_id=session_id, next_nodes=state.next)
            return Command(resume=resume), config, context

        graph_input: Any = {"messages": dump_messages(messages)}
        return graph_input, config, context

    async def get_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> list[Message]:
        """非流式获取 Deep Agent 回复（向后兼容 /chatbot/chat）。"""
        graph = await self._get_graph()
        model_name = settings.DEFAULT_LLM_MODEL
        try:
            graph_input, config, context = await self._resolve_input(
                graph, messages, session_id, user_id, username
            )
            with llm_inference_duration_seconds.labels(model=model_name).time():
                response = await graph.ainvoke(graph_input, config=config, context=context)

            state = await graph.aget_state(config)
            if state.next:
                interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "Waiting for input."
                logger.info("deep_agent_interrupted", session_id=session_id, interrupt_value=str(interrupt_value))
                return [Message(role="assistant", content=str(interrupt_value))]

            openai_msgs = cast(list[dict], convert_to_openai_messages(response["messages"]))
            asyncio.create_task(memory_service.add(user_id, openai_msgs, config.get("metadata")))
            return self.__process_messages(response["messages"])
        except GraphInterrupt:
            state = await graph.aget_state({"configurable": {"thread_id": session_id}})
            interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "Waiting for input."
            logger.info("deep_agent_interrupted", session_id=session_id, interrupt_value=str(interrupt_value))
            return [Message(role="assistant", content=str(interrupt_value))]
        except Exception as e:
            logger.exception("get_response_failed", error=str(e), session_id=session_id)
            raise

    async def get_stream_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """纯文本流式回复（向后兼容 /chatbot/chat/stream）。"""
        graph = await self._get_graph()
        try:
            graph_input, config, context = await self._resolve_input(
                graph, messages, session_id, user_id, username
            )
            async for token, _ in graph.astream(
                graph_input, config, context=context, stream_mode="messages"
            ):
                if not isinstance(token, (AIMessage, AIMessageChunk)):
                    continue
                text = extract_text_content(token.content)
                if text:
                    yield text

            state = await graph.aget_state(config)
            if state.next:
                interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "Waiting for input."
                logger.info("deep_agent_interrupted_stream", session_id=session_id, interrupt_value=str(interrupt_value))
                yield str(interrupt_value)
            elif state.values and "messages" in state.values:
                openai_msgs = cast(list[dict], convert_to_openai_messages(state.values["messages"]))
                asyncio.create_task(memory_service.add(user_id, openai_msgs, config.get("metadata")))
        except GraphInterrupt:
            state = await graph.aget_state({"configurable": {"thread_id": session_id}})
            interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "Waiting for input."
            logger.info("deep_agent_interrupted_stream", session_id=session_id, interrupt_value=str(interrupt_value))
            yield str(interrupt_value)
        except Exception as stream_error:
            logger.exception("stream_processing_failed", error=str(stream_error), session_id=session_id)
            raise stream_error

    async def get_langgraph_stream(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        resume_value: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """面向 assistant-ui ``useLangGraphRuntime`` 的结构化事件流。

        以 SSE 逐条产出 ``{"event": "messages", "data": [序列化消息, metadata]}`` 的 JSON
        字符串，可让前端渲染流式文本与工具调用（含 write_todos 规划、task 子智能体、
        文件系统与投研工具）。中断时以合成 ai 消息呈现问题；异常时产出 error 事件。

        Yields:
            str: 形如 data 前缀的 SSE 片段（每条以两个换行结尾）。
        """
        graph = await self._get_graph()

        def _sse(event: str, data: Any) -> str:
            payload = json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
            return f"data: {payload}\n\n"

        try:
            graph_input, config, context = await self._resolve_input(
                graph, messages, session_id, user_id, username, resume_value=resume_value
            )

            async for message, metadata in graph.astream(
                graph_input, config, context=context, stream_mode="messages"
            ):
                if not isinstance(message, BaseMessage):
                    continue
                # write_todos（规划）/ task（子智能体）/ 文件系统 / 投研工具的调用都会以
                # AIMessageChunk 的 tool_call_chunks 形式流出，前端据此渲染工具卡片。
                yield _sse("messages", [_serialize_message(message), metadata])

            # 流结束后：检查中断或写入长期记忆
            state = await graph.aget_state(config)
            if state.next:
                interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "Waiting for input."
                logger.info("deep_agent_interrupted_lg_stream", session_id=session_id)
                # 以合成 AI 消息形式把中断问题呈现给前端
                yield _sse(
                    "messages",
                    [{"type": "ai", "content": str(interrupt_value), "id": f"interrupt-{session_id}"}, {}],
                )
            elif state.values and "messages" in state.values:
                openai_msgs = cast(list[dict], convert_to_openai_messages(state.values["messages"]))
                asyncio.create_task(memory_service.add(user_id, openai_msgs, config.get("metadata")))
        except GraphInterrupt:
            state = await graph.aget_state({"configurable": {"thread_id": session_id}})
            interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "Waiting for input."
            logger.info("deep_agent_interrupted_lg_stream", session_id=session_id)
            yield _sse(
                "messages",
                [{"type": "ai", "content": str(interrupt_value), "id": f"interrupt-{session_id}"}, {}],
            )
        except Exception as stream_error:
            logger.exception("langgraph_stream_failed", error=str(stream_error), session_id=session_id)
            yield _sse("error", {"message": str(stream_error)})

    async def get_langgraph_history(self, session_id: str) -> list[dict]:
        """返回适配 useLangGraphRuntime ``load`` 的完整历史消息（含工具调用）。"""
        graph = await self._get_graph()
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}
        state: StateSnapshot = await graph.aget_state(config=config)
        if not state.values or "messages" not in state.values:
            return []
        result: list[dict] = []
        for message in state.values["messages"]:
            if not isinstance(message, BaseMessage):
                continue
            if message.type in ("human", "ai", "tool"):
                result.append(_serialize_message(message))
        return result

    async def get_chat_history(self, session_id: str) -> list[Message]:
        """返回指定 thread 的聊天历史（仅 user/assistant 文本，向后兼容）。"""
        graph = await self._get_graph()
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}
        state: StateSnapshot = await graph.aget_state(config=config)
        return self.__process_messages(state.values["messages"]) if state.values else []

    def __process_messages(self, messages: list[BaseMessage]) -> list[Message]:
        openai_style_messages = convert_to_openai_messages(messages)
        return [
            Message(role=message["role"], content=str(message["content"]))
            for message in openai_style_messages
            if message["role"] in ["assistant", "user"] and message["content"]
        ]

    async def clear_chat_history(self, session_id: str) -> None:
        """清除指定 thread 的全部检查点历史。"""
        try:
            conn_pool = await self._get_connection_pool()
            if conn_pool is None:
                raise RuntimeError("connection pool unavailable; cannot clear chat history")

            async with conn_pool.connection() as conn:
                async with conn.pipeline():
                    for table in settings.CHECKPOINT_TABLES:
                        await conn.execute(
                            sql.SQL("DELETE FROM {} WHERE thread_id = %s").format(sql.Identifier(table)),
                            (session_id,),
                        )
                logger.info(
                    "checkpoint_tables_cleared_for_session",
                    tables=settings.CHECKPOINT_TABLES,
                    session_id=session_id,
                )
        except Exception as e:
            logger.error("clear_chat_history_operation_failed", session_id=session_id, error=str(e))
            raise
