"""prompt 渲染：base 模板 + 市场段落拼接，纯字符串替换不引模板引擎。

注：渲染函数放在本包的 __init__.py（而非同级 prompts.py），避免
`app/services/morning_report/prompts.py`（模块）与
`app/services/morning_report/prompts/`（包）同名冲突——Python import
系统不允许同一路径下模块与包同名共存。`resources.files(__package__)`
读取的正是本目录下的 .md 模板文件。
"""

from datetime import datetime
from importlib import resources
from zoneinfo import ZoneInfo

MARKET_NAMES: dict[str, str] = {"us": "美股", "cn": "A股", "hk": "港股"}
PROMPT_KINDS: tuple[str, ...] = ("recon", "write")


def _read(filename: str) -> str:
    return (resources.files(__package__) / filename).read_text("utf-8")


def render_prompt(kind: str, market: str, trade_date: str) -> str:
    """kind: "recon" | "write"；market: us/cn/hk；trade_date: YYYY-MM-DD。"""
    if kind not in PROMPT_KINDS:
        raise ValueError(f"unknown prompt kind: {kind!r}")
    if market not in MARKET_NAMES:
        raise ValueError(f"unknown market: {market!r}")
    base = _read(f"{kind}_base.md")
    market_block = _read(f"{market}_market.md")
    text = base.replace("{{MARKET_BLOCK}}", market_block)
    return text.replace("{{TRADE_DATE}}", trade_date).replace("{{MARKET}}", MARKET_NAMES[market])


def today_beijing() -> str:
    """返回北京时间当前日期（YYYY-MM-DD），用于晨报默认交易日。"""
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
