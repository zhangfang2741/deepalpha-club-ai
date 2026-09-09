"""akshare 工具：正常返回格式化文本；接口异常时返回错误字符串而非抛异常。"""

from unittest.mock import patch

import pytest

from app.services.morning_report import data_tools


@pytest.mark.asyncio
async def test_cn_index_snapshot_formats_rows():
    fake = type("DF", (), {"empty": False, "iterrows": lambda self: iter([
        (0, {"名称": "上证指数", "最新价": 3200.5, "涨跌幅": 0.72, "成交额": 3.1e11}),
        (1, {"名称": "深证成指", "最新价": 9800.1, "涨跌幅": -0.31, "成交额": 4.2e11}),
        (2, {"名称": "创业板指", "最新价": 2000, "涨跌幅": 1, "成交额": 1e11}),
    ])})()
    with patch.object(data_tools, "_fetch_cn_index", return_value=fake):
        result = await data_tools.cn_index_snapshot.ainvoke({})
    assert "上证指数" in result and "+0.72%" in result and "-0.31%" in result
    assert "两市成交额: 7300 亿元" in result


@pytest.mark.asyncio
async def test_tool_error_returns_message_not_raise():
    with patch.object(data_tools, "_fetch_cn_index", side_effect=RuntimeError("接口超时")):
        result = await data_tools.cn_index_snapshot.ainvoke({})
    assert "失败" in result and "接口超时" in result
