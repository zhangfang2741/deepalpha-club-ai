"""交易台引擎接口。

引擎 = 整条流水线：给定标的与人工意见，产出事件异步流。DAG 编排属于
引擎内部，不上浮到本层。这是「用它而不抄它」唯一自洽的切法——若把流程
固定成我们自己的 DAG，就必须把 TradingAgents 拆开重组（等于抄了一半），
还会丢掉它的三方风控辩论。换引擎只需再写一个实现，事件协议与前端壳不动。

代价：不同引擎的流程条长得不一样。这是可接受的——引擎的差异本来就该被看见。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.schemas.trading_desk import EngineDescriptor, TradingDeskEvent


@dataclass(frozen=True)
class ControlHandle:
    """runner 交给引擎的控制句柄，让引擎在节点边界响应人机交互。

    引擎只在自己的节点边界调用这些方法——这样暂停不会把某个 agent 的
    推理拦腰截断。
    """

    is_paused: Callable[[], Awaitable[bool]]
    is_cancelled: Callable[[], Awaitable[bool]]
    drain_notes: Callable[[], Awaitable[list[str]]]


@dataclass(frozen=True)
class RunContext:
    """一次运行的上下文。"""

    run_id: str
    ticker: str
    trade_date: str
    control: ControlHandle


@runtime_checkable
class TradingEngine(Protocol):
    """交易台引擎协议。

    实现者：
      - engines/mock.py          回放固定序列，不调 LLM
      - engines/tradingagents.py 包 TradingAgents（计划三）
    """

    name: str

    def describe(self) -> EngineDescriptor:
        """自报拓扑与能力，用于填充 run.started。"""
        ...

    def astream(self, ctx: RunContext) -> AsyncIterator[TradingDeskEvent]:
        """产出事件异步流。

        不应产出 run.started / run.finished —— 这两个由 runner 统一包裹，
        保证所有引擎的生命周期语义一致。
        """
        ...
