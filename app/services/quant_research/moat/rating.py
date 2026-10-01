"""评级合成：财务证据与来源同时成立才有护城河（参照 Morningstar：超额回报 + 可说清的来源）。纯函数。"""

from __future__ import annotations

from typing import Literal

Rating = Literal["wide", "narrow", "none"]


def combine(evidence_level: str, strengths: list[str]) -> Rating:
    """宽 = 强证据 + (1 个强来源或 2 个中等来源)；窄 = 至少中等证据 + 至少 1 个中等以上来源；其余为无。"""
    strong = sum(s == "strong" for s in strengths)
    moderate = sum(s == "moderate" for s in strengths)
    if evidence_level == "strong" and (strong >= 1 or moderate >= 2):
        return "wide"
    if evidence_level in ("strong", "moderate") and strong + moderate >= 1:
        return "narrow"
    return "none"
