"""This file contains the prompts for the agent."""

import os
from datetime import datetime
from typing import Optional

from app.core.config import settings

_PROMPTS_DIR = os.path.dirname(__file__)

# Read templates once at module load — no file I/O per request
with open(os.path.join(_PROMPTS_DIR, "system.md"), "r") as _f:
    _SYSTEM_PROMPT_TEMPLATE = _f.read()

with open(os.path.join(_PROMPTS_DIR, "session_title.md"), "r") as _f:
    SESSION_TITLE_PROMPT = _f.read()

with open(os.path.join(_PROMPTS_DIR, "deep_agent.md"), "r") as _f:
    _DEEP_AGENT_PROMPT_TEMPLATE = _f.read()


def load_system_prompt(username: Optional[str] = None, **kwargs):
    """Load the system prompt from the cached template."""
    user_context = f"# User\nYou are talking to {username}.\n" if username else ""
    return _SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=settings.PROJECT_NAME + " Agent",
        current_date_and_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user_context=user_context,
        **kwargs,
    )


def load_deep_agent_prompt() -> str:
    """加载 Deep Agent 的静态系统指令（不含每轮动态上下文）。

    动态的用户信息与长期记忆通过 :func:`build_dynamic_context` 在每轮以
    独立 SystemMessage 注入，因此本模板只做一次性构建。
    """
    return _DEEP_AGENT_PROMPT_TEMPLATE.format(agent_name=settings.PROJECT_NAME + " Agent")


def build_dynamic_context(username: Optional[str] = None, long_term_memory: str = "") -> str:
    """构建每轮对话注入的动态上下文文本（用户信息 + 长期记忆 + 当前时间）。"""
    parts: list[str] = []
    if username:
        parts.append(f"# 当前用户\n你正在与 {username} 对话。")
    if long_term_memory and long_term_memory.strip():
        parts.append(f"# 关于用户的已知信息（长期记忆）\n{long_term_memory}")
    parts.append(f"# 当前日期与时间\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n\n".join(parts)
