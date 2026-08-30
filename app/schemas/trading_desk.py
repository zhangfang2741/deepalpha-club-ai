"""交易台事件协议 —— 前后端唯一契约。

任何引擎（TradingAgents / 未来的 ai-hedge-fund）都必须把自己的中间输出
映射成这里定义的事件；前端只认这套 schema。这层抽象是「前端壳可复用、
后端引擎可替换」的关键，改动需同步 frontend/lib/api/trading_desk.ts。

设计要点：
  - agent.token 是增量，前端按 turn_id 累加（不是 stage_id：一个辩论
    stage 会产生多张卡片，按 stage 累加会串台）
  - debate.turn 的 polarity 让前端无需认识具体门派即可决定配色与分栏，
    因此同一套渲染既能画多空二元辩论，也能画激进/中立/保守三方辩论
"""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.base import BaseResponse

Polarity = Literal["bull", "bear", "neutral"]
StageGroup = Literal["analyst", "system", "debate", "manager", "trader"]


class EventType(StrEnum):
    """事件类型。值即 SSE 载荷里的 type 字段。"""

    RUN_STARTED = "run.started"
    STAGE_ACTIVE = "stage.active"
    STAGE_DONE = "stage.done"
    TURN_STARTED = "turn.started"
    AGENT_TOOL_CALL = "agent.tool_call"
    AGENT_TOKEN = "agent.token"
    TURN_DONE = "turn.done"
    AGENT_SIGNAL = "agent.signal"
    DEBATE_TURN = "debate.turn"
    HUMAN_NOTE = "human.note"
    CONSENSUS_UPDATE = "consensus.update"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    VERDICT = "verdict"
    RUN_FINISHED = "run.finished"
    ERROR = "error"


class EngineCapabilities(BaseModel):
    """引擎能力声明。

    前端据此决定「暂停」「注入意见」按钮是否可用——做不到的引擎让按钮
    置灰，而不是点了没反应。
    """

    supports_pause: bool = False
    supports_inject: bool = False
    supports_resume_after_restart: bool = False


class StageDescriptor(BaseModel):
    """流程条上的一个节点。由引擎自报，前端不写死。"""

    id: str
    name: str
    role: str = ""
    group: StageGroup = "analyst"


class EngineDescriptor(BaseModel):
    """引擎自我描述，用于填充 run.started。"""

    engine: str
    capabilities: EngineCapabilities
    stages: list[StageDescriptor]


# ── 各事件的 data 载荷 ──────────────────────────────────────────────


class RunStartedData(BaseModel):
    ticker: str
    trade_date: str
    engine: str
    capabilities: EngineCapabilities
    stages: list[StageDescriptor]


class StageData(BaseModel):
    stage_id: str


class TurnStartedData(BaseModel):
    turn_id: str
    stage_id: str
    name: str
    role: str = ""
    avatar: str = ""


class ToolCallData(BaseModel):
    turn_id: str
    tool: str
    args: dict[str, Any] | None = None


class TokenData(BaseModel):
    turn_id: str
    text: str


class TurnDoneData(BaseModel):
    turn_id: str


class SignalData(BaseModel):
    stage_id: str
    name: str
    dir: Polarity
    conf: int = Field(ge=0, le=100)
    turn_id: str | None = None
    # 引擎原生产出为 False；由我们抽取而来为 True（TradingAgents 的分析师
    # 不产出结构化信号，靠 signal_extract 补齐——前端要能区分展示）
    extracted: bool = False


class DebateTurnData(BaseModel):
    stage_id: str
    debate_id: str
    side: str
    side_label: str
    polarity: Polarity
    round: int
    turn_id: str


class HumanNoteData(BaseModel):
    text: str
    # 写进了引擎状态的哪个字段，便于审计与排障
    injected_into: str | None = None


class ConsensusData(BaseModel):
    bull: int
    neutral: int
    bear: int
    lean: str


class PauseData(BaseModel):
    at_stage_id: str | None = None


class VerdictData(BaseModel):
    """对齐 TradingAgents 的 TradeRecommendation。

    warning_message 由引擎在 JSON 解析失败走 fallback 时置位，必须在
    裁决卡上显式展示，不能吞——否则用户会把降级解析出的结论当作
    正常结论。
    """

    signal: Literal["BUY", "SELL", "HOLD"]
    confidence: float = Field(ge=0.0, le=1.0)
    size_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    entry_reference_price: float | None = None
    target_price: float | None = None
    stop_loss: float | None = None
    currency: str | None = None
    time_horizon_days: int | None = None
    rationale: str = ""
    warning_message: str | None = None


class RunFinishedData(BaseModel):
    status: Literal["completed", "cancelled", "failed", "interrupted"]
    duration_ms: int = 0


class ErrorData(BaseModel):
    message: str
    stage_id: str | None = None
    fatal: bool = False


# ── 信封 ────────────────────────────────────────────────────────────


class TradingDeskEvent(BaseModel):
    """SSE 事件信封。

    seq 由 event_bus 在写入时填充（Redis 单调计数器），前端用于去重；
    SSE 的 id 字段则用 Redis Stream ID，供 Last-Event-ID 断线续读。
    """

    type: EventType
    run_id: str
    seq: int = 0
    ts: int = Field(default_factory=lambda: int(time.time() * 1000))
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def of(
        cls,
        run_id: str,
        type_: EventType,
        payload: BaseModel | None = None,
    ) -> "TradingDeskEvent":
        """由类型化载荷构造事件。载荷统一序列化为 JSON 兼容的 dict。"""
        return cls(
            type=type_,
            run_id=run_id,
            data=payload.model_dump(mode="json") if payload is not None else {},
        )

    def is_terminal(self) -> bool:
        """是否为终止事件。event_bus 的订阅者据此结束循环。"""
        return self.type is EventType.RUN_FINISHED or (
            self.type is EventType.ERROR and bool(self.data.get("fatal"))
        )


# ── 请求 / 响应 ─────────────────────────────────────────────────────


class CreateRunRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    trade_date: str | None = None  # 留空则用今天（UTC）


class CreateRunResponse(BaseResponse):
    run_id: str


class ControlAction(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    INJECT = "inject"
    CANCEL = "cancel"


class ControlRequest(BaseModel):
    action: ControlAction
    text: str | None = None  # action=inject 时必填


class ControlResponse(BaseResponse):
    accepted: bool


# ── 历史回放（持久化层） ──────────────────────────────────────────────


class RunSummary(BaseModel):
    """历史列表里的一条 run：够前端打开详情页即可。

    故意不带 turns/signals —— 详情页才查详情接口，避免列表查询把 JSON 列
    全部读出来。
    """

    run_id: str
    ticker: str
    trade_date: str
    engine: str
    status: str
    duration_ms: int
    created_at: str  # ISO 8601；序列化成字符串便于前端解析
    finished_at: str | None = None

    # verdict 的最小子集：列表卡片上展示结论（BUY/SELL/HOLD + 信心）。
    verdict_signal: str | None = None
    verdict_confidence: float | None = None

    # 列表卡片上的计数：每个分析师 / 辩论 / 工具调用一次折叠即可。
    turns_count: int = 0
    signals_count: int = 0


class RunListResponse(BaseResponse):
    runs: list[RunSummary]


class RunDetailResponse(BaseResponse):
    """单条 run 详情：包含全部 turns / signals / verdict，回放页面的全部食粮。"""

    run_id: str
    ticker: str
    trade_date: str
    engine: str
    status: str
    duration_ms: int
    created_at: str
    finished_at: str | None = None

    verdict: dict[str, Any] | None = None
    signals: list[dict[str, Any]] = Field(default_factory=list)
    turns: list[dict[str, Any]] = Field(default_factory=list)
