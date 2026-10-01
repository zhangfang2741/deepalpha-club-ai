"""护城河来源：大模型读 10-K Item 1，判断五种来源的强弱，每条判断附年报原文。

可靠性措施（校准中逐一踩过的坑）：
- 引用必须在原文里逐字出现（统一弯引号 / 破折号、剥掉两端引号后比对），否则作废、该来源降为 none；
- 模型温度为 0 也不确定：独立判断 RUNS 次，每种来源取强度中位数；
- MiniMax 偶发把列表 / 嵌套对象返回成字符串、返回空结果：解析兜底 + 重试；
- 理由文案过禁用词检查（不出现买卖导向措辞），英文理由不得含中文。
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.core.logging import logger
from app.services.llm.service import llm_service
from app.services.quant_research.copy import contains_forbidden

RUNS = 3
ATTEMPTS = 3
SOURCE_KEYS = ("intangible_assets", "switching_costs", "network_effect", "cost_advantage", "efficient_scale")
ORDER = ("none", "weak", "moderate", "strong")
_llm_gate = asyncio.Semaphore(8)

Strength = Literal["none", "weak", "moderate", "strong"]
SourceKey = Literal["intangible_assets", "switching_costs", "network_effect", "cost_advantage", "efficient_scale"]


def _parse_json_string(v: object) -> object:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


class SourceJudgement(BaseModel):
    """一种来源的判断。"""

    source: SourceKey
    strength: Strength
    reason_zh: str = Field(description="中文大白话，1~2 句，说明为什么是这个强度")
    reason_en: str = Field(description="同一理由的英文版，1~2 句，plain English")
    quotes: list[str] = Field(default_factory=list,
                              description="支撑判断的年报英文原文，逐字摘录，每条 20~300 字符；没有就留空")

    @field_validator("quotes", mode="before")
    @classmethod
    def _coerce_quotes(cls, v: object) -> object:
        """模型偶尔把单条引用返回成字符串。"""
        v = _parse_json_string(v)
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v


class MoatJudgement(BaseModel):
    """一次完整判断：五种来源 + 主要威胁。"""

    sources: list[SourceJudgement]
    threats_zh: str = Field(description="中文，1~2 句：可能侵蚀护城河的主要威胁")
    threats_en: str = Field(description="同一内容的英文版")

    @field_validator("sources", mode="before")
    @classmethod
    def _coerce_sources(cls, v: object) -> object:
        """MiniMax 走工具调用时偶尔把嵌套列表序列化成 JSON 字符串。"""
        return _parse_json_string(v)


SYSTEM = """你是严谨的股票研究员，按 Morningstar 护城河框架判断一家公司的竞争优势来源。
护城河 = 让竞争对手很难抢走这家公司超额利润的结构性原因。规模大、销量大、历史久本身都不是护城河。

五种来源，以及什么「不算」：
- intangible_assets 无形资产：让客户愿意多付钱或让对手进不来的品牌、专利、牌照、监管许可。
  不算：只是「拥有商标」的泛泛表述，没有体现溢价或排他性。
- switching_costs 转换成本：客户换掉它要付出的金钱、时间、风险或流程代价。
  不算：供应商 / 合作伙伴签了合同（那是渠道安排，不是客户的转换成本），除非原文说明换掉代价高。
- network_effect 网络效应：用户越多，产品对每个用户越有价值（如支付网络、交易平台、社交网络）。
  不算：分销网络、门店网络、航线网络、合作伙伴网络、覆盖国家多——这些是渠道规模，不是网络效应。
- cost_advantage 成本优势：成本结构持续低于对手（规模采购、独特资源、工艺、地理位置）。
  不算：只说毛利率高（那可能是定价权，归无形资产）。
- efficient_scale 有效规模：市场容量只够少数几家盈利，新进入者进来会让所有人都不赚钱（如管道、机场、区域垄断）。
  不算：市场份额大、销量大。

强度：strong = 原文明确描述了该机制且是公司核心；moderate = 有明确描述但只覆盖部分业务；
weak = 只有间接迹象；none = 原文没有证据。拿不准时取较低的一档。

规则：
- 只依据给定的年报原文，不用你自己的背景知识补充。
- quotes 必须从原文逐字复制（英文，保留原标点），不能改写、翻译、省略或拼接，两端不要加引号；每条 20~300 字符。
- reason_zh 用中文大白话写给普通投资者；reason_en 是同一内容的英文版。都不出现买入、卖出、推荐、看多、看空、
  buy、sell、recommend 等字样，也不出现数据供应商名称。
- 五种来源都要给出判断，各一条。"""

_PUNCT = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-",
                        "—": "-", "‑": "-", "­": None, " ": " "})


def _norm(s: str) -> str:
    """比对用：统一弯引号 / 破折号 / 软连字符，压缩空白，忽略大小写。"""
    return re.sub(r"\s+", " ", s.translate(_PUNCT)).strip().lower()


def _strip_wrapping(q: str) -> str:
    """模型常在引用两端加引号或省略号，比对前剥掉（不改动中间内容）。"""
    return q.strip().strip("\"'“”‘’").strip().strip("…").strip(".").strip()


def verify_quotes(j: MoatJudgement, section: str) -> MoatJudgement:
    """只保留在原文里逐字出现的引用；判了强度却没有任何可核实引用 → 降为 none。"""
    hay = _norm(section)
    for s in j.sources:
        s.quotes = [q for q in (_strip_wrapping(x) for x in s.quotes) if len(_norm(q)) >= 20 and _norm(q) in hay]
        if s.strength != "none" and not s.quotes:
            s.strength = "none"
    return j


def _valid(j: MoatJudgement | None) -> bool:
    if j is None or {s.source for s in j.sources} != set(SOURCE_KEYS) or len(j.sources) != len(SOURCE_KEYS):
        return False
    texts = [t for s in j.sources for t in (s.reason_zh, s.reason_en)] + [j.threats_zh, j.threats_en]
    if any(contains_forbidden(t) for t in texts):
        return False
    english = [s.reason_en for s in j.sources] + [j.threats_en]
    return not any(re.search(r"[一-鿿]", t) for t in english)


async def judge_once(section: str, symbol: str) -> MoatJudgement:
    """一次判断（含重试与引用核对）。"""
    msgs = [SystemMessage(SYSTEM), HumanMessage(f"公司代码：{symbol}\n\n年报 Item 1（业务）原文：\n\n{section}")]
    last: Exception | None = None
    for _ in range(ATTEMPTS):
        try:
            async with _llm_gate:
                out = await llm_service.call(msgs, response_format=MoatJudgement, temperature=0)
        except Exception as e:  # noqa: BLE001 结构化输出偶发失败，重试
            last = e
            continue
        if _valid(out):
            return verify_quotes(out, section)  # type: ignore[arg-type]
    raise RuntimeError(f"moat judgement failed after {ATTEMPTS} attempts: {last}")


def merge_votes(runs: list[MoatJudgement]) -> MoatJudgement:
    """每种来源取强度中位数；理由与引用取自强度等于中位数的那一次；威胁取第一次。"""
    merged: list[SourceJudgement] = []
    for key in SOURCE_KEYS:
        picks = [next(s for s in r.sources if s.source == key) for r in runs]
        median = sorted(ORDER.index(p.strength) for p in picks)[len(picks) // 2]
        merged.append(next(p for p in picks if ORDER.index(p.strength) == median))
    return MoatJudgement(sources=merged, threats_zh=runs[0].threats_zh, threats_en=runs[0].threats_en)


async def judge(section: str, symbol: str) -> tuple[MoatJudgement, list[list[str]]]:
    """独立判断 RUNS 次并合并；同时返回每种来源的投票（便于排查波动）。"""
    runs = await asyncio.gather(*(judge_once(section, symbol) for _ in range(RUNS)))
    votes = [[next(s for s in r.sources if s.source == k).strength for r in runs] for k in SOURCE_KEYS]
    merged = merge_votes(list(runs))
    logger.info("quant_moat_judged", symbol=symbol, votes=votes)
    return merged, votes
