"""subprocess 沙箱测试（Linux only）"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from app.services.skills.sandbox import run_in_subprocess
from app.services.skills.errors import SkillSandboxError, SkillTimeoutError


@pytest.mark.asyncio
async def test_basic_factor_computation():
    """基本因子计算"""
    code = """
def compute(prices, symbol):
    closes = [p['close'] for p in prices]
    result = []
    for i in range(10, len(closes)):
        result.append({'time': prices[i]['date'], 'value': closes[i] / closes[i-10] - 1})
    return result
"""
    fake_prices = [
        {"date": f"2024-01-{d:02d}", "close": 100 + d * 0.5,
         "open": 100, "high": 102, "low": 99, "volume": 1000}
        for d in range(1, 61)
    ]
    result, ot = await run_in_subprocess(
        code, fake_prices, "TEST", "2024-01-01", "2024-03-01"
    )
    assert len(result) > 0
    assert all("value" in r for r in result)


@pytest.mark.asyncio
async def test_dangerous_import_blocked():
    """危险 import 被 AST 拦截"""
    code = "import os; def compute(p, s): return []"
    with pytest.raises(Exception):
        await run_in_subprocess(code, [], "TEST", "2024-01-01", "2024-01-10")


@pytest.mark.skipif(sys.platform == "darwin", reason="preexec_fn not supported on macOS")
@pytest.mark.asyncio
async def test_sandbox_timeout_kills_process():
    """超时杀掉进程"""
    code = """
import time
def compute(prices, symbol):
    time.sleep(60)
    return []
"""
    with pytest.raises(SkillTimeoutError):
        await run_in_subprocess(
            code, [], "TEST", "2024-01-01", "2024-01-10", timeout=3.0
        )