"""八字 AI 解读的 prompt 模板：daily(今日运势) / deep(深度解读)。"""

import os

_PROMPTS_DIR = os.path.dirname(__file__)

with open(os.path.join(_PROMPTS_DIR, "daily.md"), "r") as _f:
    DAILY_PROMPT = _f.read()

with open(os.path.join(_PROMPTS_DIR, "deep.md"), "r") as _f:
    DEEP_PROMPT = _f.read()
