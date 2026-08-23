"""缠论分析文案的中英切换。

前端在请求里带 `lang`（zh / en）；这里只提供一个判定与选择的小工具，
各生成函数用 `pick(lang, 中文, 英文)` 产出对应语言的文案。缠论术语用通行英译：
笔=stroke，线段=segment，中枢=pivot/hub，分型=fractal，背驰=divergence。
"""
from __future__ import annotations


def is_en(lang: str | None) -> bool:
    """是否输出英文。仅 en* 视为英文，其余（含 None/zh）走中文。"""
    return str(lang or "zh").lower().startswith("en")


def pick(lang: str | None, zh: str, en: str) -> str:
    """按语言二选一。"""
    return en if is_en(lang) else zh
