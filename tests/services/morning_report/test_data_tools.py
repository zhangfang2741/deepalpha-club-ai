"""akshare/yfinance 工具：正常返回格式化文本；接口异常时返回错误字符串而非抛异常。"""

from unittest.mock import patch

import pandas as pd
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


def _fake_us_snapshot_df() -> pd.DataFrame:
    """两日收盘价的 MultiIndex DataFrame，模拟 yf.download(group_by='ticker') 的结构。"""
    dates = pd.to_datetime(["2026-09-08", "2026-09-09"])
    columns = pd.MultiIndex.from_tuples(
        [("^GSPC", "Close"), ("^VIX", "Close")], names=["Ticker", "Price"]
    )
    return pd.DataFrame([[7670.0, 17.5], [7636.36, 18.4]], index=dates, columns=columns)


@pytest.mark.asyncio
async def test_us_index_snapshot_formats_rows():
    with patch.object(data_tools, "_fetch_us_snapshot", return_value=_fake_us_snapshot_df()):
        result = await data_tools.us_index_snapshot.ainvoke({})
    assert "标普500" in result and "7636.36" in result
    assert "-0.44%" in result  # (7636.36-7670)/7670
    assert "VIX" in result and "+5.14%" in result


@pytest.mark.asyncio
async def test_us_index_snapshot_error_returns_message_not_raise():
    with patch.object(data_tools, "_fetch_us_snapshot", side_effect=RuntimeError("超时")):
        result = await data_tools.us_index_snapshot.ainvoke({})
    assert "失败" in result and "超时" in result


@pytest.mark.asyncio
async def test_us_index_snapshot_handles_missing_ticker():
    """某个 ticker 下载失败/缺列时跳过它，不整体报错。"""
    dates = pd.to_datetime(["2026-09-08", "2026-09-09"])
    columns = pd.MultiIndex.from_tuples([("^GSPC", "Close")], names=["Ticker", "Price"])
    df = pd.DataFrame([[7670.0], [7636.36]], index=dates, columns=columns)
    with patch.object(data_tools, "_fetch_us_snapshot", return_value=df):
        result = await data_tools.us_index_snapshot.ainvoke({})
    assert "标普500" in result
    assert "VIX" not in result
