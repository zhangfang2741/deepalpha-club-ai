"""TradingAgentsEngine HITL 行为：暂停停在节点边界、注入进下游 prompt、取消早停。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.schemas.trading_desk import EventType
from app.services.trading_desk.engine_base import ControlHandle, RunContext
from app.services.trading_desk.engines.tradingagents import TradingAgentsEngine
from tests.services.trading_desk.test_ta_engine import FakeLLM


@pytest.mark.asyncio
async def test_injected_note_reaches_downstream_state(tmp_path: Path) -> None:
    """注入的意见必须出现在引擎 state 的目标字段（spec §5.3 核心承诺）。

    验证策略：等引擎流到 News Analyst 之后才放行注入——这样注入写进
    news_report 时不会被节点自身的产出覆盖。跑完之后 aget_state 看
    news_report 字段包含注入文本。
    """
    from app.services.trading_desk.engines import stage_map

    fake = FakeLLM()
    notes = ["【人工意见】把出口管制风险的权重调高。"]

    async def no() -> bool:
        return False

    order = list(stage_map.AGENT_NODES)
    post_news_call = order.index("News Analyst") + 1  # 调用计数大于此才放行

    call_count = {"n": 0}

    async def drain_after_news() -> list[str]:
        call_count["n"] += 1
        if call_count["n"] >= post_news_call:
            return list(notes)
        return []

    ctx = RunContext(
        run_id="r1", ticker="NVDA", trade_date="2026-08-30",
        control=ControlHandle(is_paused=no, is_cancelled=no, drain_notes=drain_after_news),
    )

    engine = TradingAgentsEngine(checkpointer=InMemorySaver(), results_dir=tmp_path, llm_override=fake)
    events = [e async for e in engine.astream(ctx)]
    notes_ev = [e for e in events if e.type is EventType.HUMAN_NOTE]
    assert notes_ev, f"应当至少一条 human.note 事件（注入窗口：{notes}）。events: {len(events)}"
    assert notes_ev[0].data["injected_into"] == "news_report"
    assert "把出口管制风险的权重调高" in notes_ev[0].data["text"]

    # 终态验证
    cfg = {"configurable": {"thread_id": "r1"}}
    final = await engine._compiled.aget_state(cfg)  # type: ignore[attr-defined]
    values = final.values if isinstance(final.values, dict) else vars(final.values)
    news_report = str(values.get("news_report", ""))
    assert "把出口管制风险的权重调高" in news_report, (
        f"news_report 字段应包含注入文本。实际：{news_report[:200]}"
    )


@pytest.mark.asyncio
async def test_pause_holds_at_boundary_and_resume_completes(tmp_path: Path) -> None:
    """暂停期间无新事件；解除后跑完并发出 verdict。"""
    paused = {"flag": True}

    async def is_paused() -> bool:
        return paused["flag"]

    async def no() -> bool:
        return False

    async def empty() -> list[str]:
        return []

    ctx = RunContext(
        run_id="r1", ticker="NVDA", trade_date="2026-08-30",
        control=ControlHandle(is_paused=is_paused, is_cancelled=no, drain_notes=empty),
    )

    engine = TradingAgentsEngine(
        checkpointer=InMemorySaver(), results_dir=tmp_path, llm_override=FakeLLM()
    )

    collected: list[Any] = []

    async def collect() -> None:
        async for e in engine.astream(ctx):
            collected.append(e)

    task = asyncio.ensure_future(collect())
    # interrupt_before 让首轮 astream 立即在 Market Analyst 进入前暂停；
    # 此时还没有事件可观察——等 pause 解除后再断言
    await asyncio.sleep(0.3)
    pre_resume_count = len(collected)
    assert pre_resume_count == 0, (
        f"interrupt_before 应让首轮在节点边界暂停，暂停时不应出事件；"
        f"实测出了 {pre_resume_count} 个"
    )

    paused["flag"] = False  # 解除暂停
    await asyncio.wait_for(task, timeout=60)

    assert any(e.type is EventType.VERDICT for e in collected), "解除暂停后必须跑完并发出 verdict"


@pytest.mark.asyncio
async def test_cancel_short_circuits_run(tmp_path: Path) -> None:
    """取消应当尽早停止：不发 verdict 但不报错。"""
    cancel = {"flag": False}

    async def is_cancelled() -> bool:
        return cancel["flag"]

    async def no() -> bool:
        return False

    async def empty() -> list[str]:
        return []

    ctx = RunContext(
        run_id="r1", ticker="NVDA", trade_date="2026-08-30",
        control=ControlHandle(is_paused=no, is_cancelled=is_cancelled, drain_notes=empty),
    )

    engine = TradingAgentsEngine(
        checkpointer=InMemorySaver(), results_dir=tmp_path, llm_override=FakeLLM()
    )

    events: list[Any] = []

    async def collect() -> None:
        async for e in engine.astream(ctx):
            events.append(e)
            if len(events) >= 2:  # 等事件开始流
                cancel["flag"] = True

    await asyncio.wait_for(collect(), timeout=30)

    assert not any(e.type is EventType.VERDICT for e in events), "取消应当早停，不发 verdict"
