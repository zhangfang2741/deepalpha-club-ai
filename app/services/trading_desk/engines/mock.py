"""MockEngine —— 回放一段固定的分析剧本，不调用任何 LLM。

用途有三，缺一不可：
  1. 前端联调：没有 LLM 成本与延迟，交互体感可以反复打磨
  2. 集成测试与 CI：runner / event_bus / SSE / HITL 全链路可测
  3. 「引擎可替换」抽象的第一个验证者 —— 它与 TradingAgentsEngine
     共用同一个接口，说明将来接 ai-hedge-fund 也能

剧本内容取自交互原型 docs/floor-prototype-cn.html，仅用于打磨交互，
不构成任何投资观点。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.schemas.trading_desk import (
    ConsensusData,
    DebateTurnData,
    EngineCapabilities,
    EngineDescriptor,
    EventType,
    HumanNoteData,
    Polarity,
    SignalData,
    StageData,
    StageDescriptor,
    TokenData,
    ToolCallData,
    TradingDeskEvent,
    TurnDoneData,
    TurnStartedData,
    VerdictData,
)
from app.services.trading_desk.engine_base import RunContext

_STAGES = [
    StageDescriptor(id="fundamentals", name="基本面分析师", role="价值", group="analyst"),
    StageDescriptor(id="market", name="技术面分析师", role="价格行为", group="analyst"),
    StageDescriptor(id="news", name="消息与情绪", role="资讯流", group="analyst"),
    StageDescriptor(id="research_debate", name="研究员辩论", role="多空对辩", group="debate"),
    StageDescriptor(id="trader", name="交易员", role="综合", group="trader"),
    StageDescriptor(id="risk", name="风控委员会", role="约束", group="debate"),
    StageDescriptor(id="pm", name="投资组合经理", role="裁决", group="manager"),
]


@dataclass(frozen=True)
class _DebateMeta:
    debate_id: str
    side: str
    side_label: str
    polarity: Polarity
    round: int


@dataclass(frozen=True)
class _Beat:
    """剧本里的一拍：一个 agent 的一次发言。"""

    stage_id: str
    turn_id: str
    name: str
    role: str
    avatar: str
    text: str
    tools: tuple[str, ...] = ()
    signal: tuple[Polarity, int] | None = None
    debate: _DebateMeta | None = field(default=None)


_SCRIPT: tuple[_Beat, ...] = (
    _Beat(
        stage_id="fundamentals",
        turn_id="fundamentals-1",
        name="基本面分析师",
        role="价值",
        avatar="FA",
        tools=("financials.get", "earnings.get"),
        text=(
            "{ticker} 的核心业务营收仍在复合增长，但同比增速已在高基数上放缓。毛利率依旧优秀（约 73%）。"
            "前瞻市盈率约 35 倍，已经把「持续统治」定价进去了——公司质地一流，但安全边际很薄。"
        ),
        signal=("neutral", 55),
    ),
    _Beat(
        stage_id="market",
        turn_id="market-1",
        name="技术面分析师",
        role="价格行为",
        avatar="TA",
        tools=("ohlcv.get", "indicators.calc"),
        text=(
            "回调后重新站上 50 日均线，更高低点的结构完好。RSI 61，有动能但还没超买。"
            "上涨日成交量配合。下方支撑清晰，前高是头顶的阻力位。"
        ),
        signal=("bull", 64),
    ),
    _Beat(
        stage_id="news",
        turn_id="news-1",
        name="消息与情绪",
        role="资讯流",
        avatar="NA",
        tools=("news.search", "sentiment.score"),
        text=(
            "消息面喜忧参半：下游大客户的资本开支指引强劲是顺风，但出口管制的噪音、"
            "以及关键客户培育第二供应源的动作是压制项。近期净情绪：谨慎偏正面。"
        ),
        signal=("bull", 58),
    ),
    _Beat(
        stage_id="research_debate",
        turn_id="research-r1-bull",
        name="多头研究员",
        role="第 1 轮",
        avatar="BR",
        debate=_DebateMeta("research", "bull", "多头研究员", "bull", 1),
        text=(
            "这不是一个季度的故事。前几大客户的资本开支承诺是多年期的，当下也没有能规模化"
            "替代的方案。就算从纪录高基数上放缓，那也还是 40%+ 的增速。"
        ),
    ),
    _Beat(
        stage_id="research_debate",
        turn_id="research-r1-bear",
        name="空头研究员",
        role="第 1 轮",
        avatar="BE",
        debate=_DebateMeta("research", "bear", "空头研究员", "bear", 1),
        text=(
            "那正是「一致预期交易」——这本身就是风险，所有人都持有。只要出现一个消化资本开支"
            "的季度、或一个可信的竞争者，在这种估值下就会被狠狠杀跌。集中度风险是实打实的。"
        ),
    ),
    _Beat(
        stage_id="research_debate",
        turn_id="research-r2-bull",
        name="多头研究员",
        role="第 2 轮",
        avatar="BR",
        debate=_DebateMeta("research", "bull", "多头研究员", "bull", 2),
        text=(
            "估值确实贵，我认。但你买的是这场仍处早期的淘金热里唯一的「铲子」。"
            "{ticker} 生态与软件栈的锁定效应被低估了——护城河不只是硬件本身。"
        ),
        signal=("bull", 70),
    ),
    _Beat(
        stage_id="research_debate",
        turn_id="research-r2-bear",
        name="空头研究员",
        role="第 2 轮",
        avatar="BE",
        debate=_DebateMeta("research", "bear", "空头研究员", "bear", 2),
        text=(
            "锁定是真的，但不是永久的——大客户砸钱要绕开的恰恰就是它。我不做空，"
            "我是说：按「一条消息就能跳空 15%」的仓位来管理它。"
        ),
        signal=("bear", 60),
    ),
    _Beat(
        stage_id="trader",
        turn_id="trader-1",
        name="交易员",
        role="综合",
        avatar="TR",
        text="结论：{ticker} 逻辑成立，但这个估值下入场点很关键。建议先建底仓，回调到支撑再加——现在不上满仓。",
    ),
    _Beat(
        stage_id="risk",
        turn_id="risk-1",
        name="风控委员会",
        role="约束",
        avatar="RC",
        text=(
            "标记：单一标的集中度，以及约 3 周后财报的事件风险。初始仓位上限 4%，"
            "硬止损 -8%，财报前不加仓。带约束批准。"
        ),
    ),
    _Beat(
        stage_id="pm",
        turn_id="pm-1",
        name="投资组合经理",
        role="最终决策",
        avatar="PM",
        text=(
            "决策：买入 {ticker}，底仓。需求的持续性 + 技术结构盖过估值风险——"
            "但要在缩小仓位、并锁进风控约束的前提下执行。"
        ),
    ),
)

_VERDICT = VerdictData(
    signal="BUY",
    confidence=0.66,
    size_fraction=0.04,
    entry_reference_price=178.2,
    target_price=205.0,
    stop_loss=163.9,
    currency="USD",
    time_horizon_days=21,
    rationale="多头共识（5 个信号中 3 个偏多）被高估值和事件风险抵消。小仓位入场，回调加仓，财报后重新评估。",
)

# 每次 token 切片的字符数。切得太细会让事件量爆炸，太粗则失去流式观感。
_CHUNK = 6


class MockEngine:
    """回放固定剧本的引擎实现。"""

    name = "mock"

    def __init__(self, tick_seconds: float = 0.03) -> None:
        """初始化。

        Args:
            tick_seconds: 每个 token 片段之间的间隔。测试传 0 跑满速；
                前端联调传 0.03 左右可获得接近真实的流式观感。
        """
        self._tick = tick_seconds

    def describe(self) -> EngineDescriptor:
        """自报拓扑与能力。"""
        return EngineDescriptor(
            engine="mock/1",
            capabilities=EngineCapabilities(
                supports_pause=True,
                supports_inject=True,
                supports_resume_after_restart=False,
            ),
            stages=list(_STAGES),
        )

    async def astream(self, ctx: RunContext) -> AsyncIterator[TradingDeskEvent]:
        """按剧本产出事件，并在每一拍的边界响应暂停 / 取消 / 注入。"""
        run_id = ctx.run_id
        signals: list[tuple[Polarity, int]] = []
        active_stage: str | None = None

        for beat in _SCRIPT:
            # 节点边界：先处理取消与暂停，再吐人工意见
            if await ctx.control.is_cancelled():
                return

            while await ctx.control.is_paused():
                if await ctx.control.is_cancelled():
                    return
                await asyncio.sleep(max(self._tick, 0.05))

            for note in await ctx.control.drain_notes():
                yield TradingDeskEvent.of(
                    run_id,
                    EventType.HUMAN_NOTE,
                    HumanNoteData(text=note, injected_into="news_report"),
                )

            if beat.stage_id != active_stage:
                if active_stage is not None:
                    yield TradingDeskEvent.of(run_id, EventType.STAGE_DONE, StageData(stage_id=active_stage))
                active_stage = beat.stage_id
                yield TradingDeskEvent.of(run_id, EventType.STAGE_ACTIVE, StageData(stage_id=active_stage))

            yield TradingDeskEvent.of(
                run_id,
                EventType.TURN_STARTED,
                TurnStartedData(
                    turn_id=beat.turn_id,
                    stage_id=beat.stage_id,
                    name=beat.name,
                    role=beat.role,
                    avatar=beat.avatar,
                ),
            )

            if beat.debate is not None:
                d = beat.debate
                yield TradingDeskEvent.of(
                    run_id,
                    EventType.DEBATE_TURN,
                    DebateTurnData(
                        stage_id=beat.stage_id,
                        debate_id=d.debate_id,
                        side=d.side,
                        side_label=d.side_label,
                        polarity=d.polarity,
                        round=d.round,
                        turn_id=beat.turn_id,
                    ),
                )

            for tool in beat.tools:
                yield TradingDeskEvent.of(
                    run_id, EventType.AGENT_TOOL_CALL, ToolCallData(turn_id=beat.turn_id, tool=tool)
                )
                await asyncio.sleep(self._tick)

            text = beat.text.format(ticker=ctx.ticker)
            for i in range(0, len(text), _CHUNK):
                yield TradingDeskEvent.of(
                    run_id,
                    EventType.AGENT_TOKEN,
                    TokenData(turn_id=beat.turn_id, text=text[i : i + _CHUNK]),
                )
                await asyncio.sleep(self._tick)

            yield TradingDeskEvent.of(run_id, EventType.TURN_DONE, TurnDoneData(turn_id=beat.turn_id))

            if beat.signal is not None:
                direction, conf = beat.signal
                signals.append(beat.signal)
                yield TradingDeskEvent.of(
                    run_id,
                    EventType.AGENT_SIGNAL,
                    SignalData(
                        stage_id=beat.stage_id,
                        turn_id=beat.turn_id,
                        name=beat.name,
                        dir=direction,
                        conf=conf,
                    ),
                )
                yield TradingDeskEvent.of(run_id, EventType.CONSENSUS_UPDATE, _consensus(signals))

        if active_stage is not None:
            yield TradingDeskEvent.of(run_id, EventType.STAGE_DONE, StageData(stage_id=active_stage))

        yield TradingDeskEvent.of(run_id, EventType.VERDICT, _VERDICT)


def _consensus(signals: list[tuple[Polarity, int]]) -> ConsensusData:
    """按方向计数并给出倾向描述。与前端自算保持同一套口径。"""
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
