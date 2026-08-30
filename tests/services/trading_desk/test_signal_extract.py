"""信号抽取：从分析师报告文本抽 {dir, conf}。"""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.services.trading_desk import signal_extract


def test_prompt_asks_for_strict_json() -> None:
    prompt = signal_extract.build_prompt("基本面", "营收增长但估值偏高。")
    assert "bull" in prompt and "bear" in prompt and "neutral" in prompt
    assert "conf" in prompt


async def test_extract_parses_valid_json() -> None:
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value='{"dir": "bull", "conf": 72}')

    result = await signal_extract.extract_signal(fake_llm, stage_name="基本面", report="……")  # type: ignore[arg-type]

    assert result == ("bull", 72)


async def test_extract_parses_json_in_code_block() -> None:
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value='好的，这是我的判断：\n```json\n{"dir": "bear", "conf": 64}\n```')

    result = await signal_extract.extract_signal(fake_llm, stage_name="基本面", report="……")  # type: ignore[arg-type]

    assert result == ("bear", 64)


async def test_extract_clamps_confidence() -> None:
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value='{"dir": "bull", "conf": 130}')

    result = await signal_extract.extract_signal(fake_llm, stage_name="基本面", report="……")  # type: ignore[arg-type]

    assert result == ("bull", 100)


async def test_extract_degrades_to_neutral_on_garbage() -> None:
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value="模型抽风了，这不是 JSON")

    result = await signal_extract.extract_signal(fake_llm, stage_name="基本面", report="……")  # type: ignore[arg-type]

    # 降级为中性低置信，绝不静默编方向（spec §4.6）
    assert result[0] == "neutral"
    assert result[1] < 50


async def test_extract_degrades_on_invalid_dir() -> None:
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value='{"dir": "sideways", "conf": 80}')

    result = await signal_extract.extract_signal(fake_llm, stage_name="基本面", report="……")  # type: ignore[arg-type]

    assert result[0] == "neutral"


async def test_extract_degrades_on_empty_report() -> None:
    fake_llm = AsyncMock()

    result = await signal_extract.extract_signal(fake_llm, stage_name="基本面", report="   ")  # type: ignore[arg-type]

    assert result[0] == "neutral"
    fake_llm.ainvoke.assert_not_awaited()


async def test_extract_degrades_on_exception() -> None:
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("超时"))

    result = await signal_extract.extract_signal(fake_llm, stage_name="基本面", report="……")  # type: ignore[arg-type]

    assert result[0] == "neutral"
