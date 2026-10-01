"""护城河校准（一次性脚本，只读）：证据（10 年 ROIC vs 资金成本）+ 来源（大模型读 10-K）。

用法（需线上 FMP / LLM 配置）：railway run uv run python scripts/moat_calibration.py [SYMBOL ...]
只做只读调用（FMP / SEC / LLM），不写数据库与 Redis；FMP 调用串行、经全局预算限流。
结果写到 data/moat_calibration/（git 忽略）。
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import warnings
from pathlib import Path
from typing import Literal

import httpx
from bs4 import BeautifulSoup
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.services.llm.service import llm_service
from app.services.quant_research.copy import contains_forbidden
from app.services.quant_research.fmp import FmpClient

OUT_DIR = Path("data/moat_calibration")
SEC_HEADERS = {"User-Agent": "DeepAlpha research contact@deepalpha.club", "Accept-Encoding": "gzip, deflate"}
RISK_FREE = 0.043     # 10 年期美债收益率近似
EQUITY_PREMIUM = 0.05
TAX = 0.21
SECTION_CHARS = 45_000

# 公开报道中较常见的 Morningstar 评级（可能已调整，仅作校准参照）
EXPECTED = {
    "KO": "wide", "MSFT": "wide", "V": "wide", "MA": "wide", "PG": "wide", "GOOGL": "wide", "ADBE": "wide",
    "F": "none", "GM": "none", "UAL": "none", "AAL": "none", "M": "none",
}
EXTRA = ["NVDA", "COST", "INTC"]  # 无确定参照，只看推理是否合理

SourceKey = Literal["intangible_assets", "switching_costs", "network_effect", "cost_advantage", "efficient_scale"]
SOURCE_ZH = {"intangible_assets": "无形资产", "switching_costs": "转换成本", "network_effect": "网络效应",
             "cost_advantage": "成本优势", "efficient_scale": "有效规模"}


# ---------------- 证据：ROIC vs 资金成本 ----------------

async def evidence(fmp: FmpClient, symbol: str) -> dict:
    km = await fmp.get("key-metrics", symbol=symbol, period="annual", limit=10) or []
    prof = (await fmp.get("profile", symbol=symbol) or [{}])[0]
    bal = (await fmp.get("balance-sheet-statement", symbol=symbol, period="annual", limit=1) or [{}])[0]
    years = sorted(((int(r["fiscalYear"]), r.get("returnOnInvestedCapital")) for r in km
                    if r.get("returnOnInvestedCapital") is not None), reverse=True)
    beta = prof.get("beta") or 1.0
    mcap, debt = prof.get("marketCap") or 0, bal.get("totalDebt") or 0
    ke = min(max(RISK_FREE + beta * EQUITY_PREMIUM, 0.06), 0.14)
    kd = (RISK_FREE + 0.015) * (1 - TAX)
    wacc = (mcap * ke + debt * kd) / (mcap + debt) if mcap + debt > 0 else ke
    spreads = [roic - wacc for _, roic in years]
    n = len(spreads)
    above = sum(s > 0 for s in spreads)
    avg = sum(spreads) / n if n else None
    trend = (sum(spreads[:3]) / 3 - sum(spreads[-3:]) / 3) if n >= 6 else None  # 近 3 年 − 早 3 年
    if n >= 8 and above >= n - 1 and (avg or 0) >= 0.03:  # 校准：5% 会把 KO 判成窄
        level = "strong"
    elif n >= 5 and above >= 0.7 * n and (avg or 0) > 0:
        level = "moderate"
    else:
        level = "weak"
    return {"years": years, "beta": beta, "wacc": round(wacc, 4), "years_above": above, "n_years": n,
            "avg_spread": round(avg, 4) if avg is not None else None,
            "trend": round(trend, 4) if trend is not None else None, "level": level}


# ---------------- 来源：10-K Item 1 ----------------

_TICKERS: dict[str, int] = {}


async def tenk_business(client: httpx.AsyncClient, symbol: str) -> tuple[str, str] | None:
    """最新 10-K 的 Item 1（业务）文本与链接。"""
    if not _TICKERS:
        r = await client.get("https://www.sec.gov/files/company_tickers.json", headers=SEC_HEADERS)
        _TICKERS.update({v["ticker"]: v["cik_str"] for v in r.json().values()})
    cik = _TICKERS.get(symbol.replace(".", "-"))
    if cik is None:
        return None
    sub = (await client.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=SEC_HEADERS)).json()
    recent = sub["filings"]["recent"]
    idx = next((i for i, f in enumerate(recent["form"]) if f == "10-K"), None)
    if idx is None:
        return None
    acc = recent["accessionNumber"][idx].replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{recent['primaryDocument'][idx]}"
    html = (await client.get(url, headers=SEC_HEADERS, timeout=60)).text
    section = extract_business(html)
    return (section, url) if section else None


_KEYWORDS = re.compile(r"compet|trademark|patent|brand|licens|switching|network|scale|cost|market share|"
                       r"customer|contract|regulat|barrier|proprietary|intellectual property", re.I)


def extract_business(html: str) -> str | None:
    """10-K 正文的 Item 1（业务）：取行首「ITEM 1 业务」标题到「ITEM 1A 风险因素」标题之间的正文
    （目录里的同名条目只隔几十个字符，取最长的一段）。超长时保留开头 + 竞争 / 商标 / 专利等关键词段落。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = BeautifulSoup(html, "lxml").get_text("\n")
    text = re.sub(r"[ \t\xa0\u2002\u2003\u2009\u200b]+", " ", raw)
    text = re.sub(r"\n\s*\n+", "\n", text)
    # 每个「1A 风险因素」标题与上一个之间，取第一个「1 业务」标题：避开目录，也避开每页页眉重复的「ITEM 1. BUSINESS」
    best, prev = "", 0
    for e in (m.start() for m in re.finditer(r"(?im)^\W*item\W*1a\W*(?:\n\W*)?risk\W*factors\W*$", text)):
        first = re.search(r"(?im)^\W*item\W*1(?![0-9a-z])\W*(?:\n\W*)?business\W*$", text[prev:e])
        if first and e - (prev + first.start()) > len(best):
            best = text[prev + first.start():e]
        prev = e
    if len(best) < 2000:
        return _keyword_fallback(text)
    if len(best) <= SECTION_CHARS:
        return best
    head, rest = best[:30_000], best[30_000:].split("\n")
    picked = [para for para in rest if _KEYWORDS.search(para)]
    tail = "\n".join(picked)[: SECTION_CHARS - len(head)]
    return head + "\n…\n" + tail


def _keyword_fallback(text: str) -> str | None:
    """非标准 10-K（如只有页眉、条目对照表放在文末）：取前 60% 正文里讲竞争 / 品牌 / 专利 / 客户的长段落。"""
    body = text[: int(len(text) * 0.6)]
    paras = [p for p in body.split("\n") if len(p) >= 200 and _KEYWORDS.search(p)]
    joined = "\n".join(paras)[:SECTION_CHARS]
    return joined if len(joined) > 2000 else None


class SourceJudgement(BaseModel):
    source: SourceKey
    strength: Literal["none", "weak", "moderate", "strong"]
    reason: str = Field(description="中文大白话，1~2 句，说明为什么是这个强度")
    raw_quotes: list[str] = Field(default_factory=list, description="（内部用，不要填写）")
    votes: list[str] = Field(default_factory=list, description="（内部用，不要填写）")
    quotes: list[str] = Field(default_factory=list,
                              description="支撑判断的年报英文原文，逐字摘录，每条不超过 300 字符；没有就留空")

    @field_validator("quotes", mode="before")
    @classmethod
    def _coerce_quotes(cls, v: object) -> object:
        """模型偶尔把单条引用返回成字符串，包成列表；空串视为没有。"""
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v


class MoatSources(BaseModel):
    sources: list[SourceJudgement]

    @field_validator("sources", mode="before")
    @classmethod
    def _parse_json_string(cls, v: object) -> object:
        """MiniMax 走工具调用时偶尔把嵌套列表序列化成 JSON 字符串。"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except ValueError:
                return v
        return v

    threats: str = Field(description="中文，1~2 句：可能侵蚀护城河的主要威胁")


SYSTEM = """你是严谨的股票研究员，按 Morningstar 护城河框架判断一家公司的竞争优势来源。
护城河 = 让竞争对手很难抢走这家公司超额利润的结构性原因。规模大、销量大、历史久本身都不是护城河。

五种来源，以及什么「不算」：
- intangible_assets 无形资产：让客户愿意多付钱或让对手进不来的品牌、专利、牌照、监管许可。
  不算：只是「拥有商标」的泛泛表述，没有体现溢价或排他性。
- switching_costs 转换成本：客户换掉它要付出的金钱、时间、风险或流程代价。
  不算：供应商 / 合作伙伴签了合同（那是渠道安排，不是客户的转换成本），除非原文说明换掉代价高。
- network_effect 网络效应：用户越多，产品对每个用户越有价值（如支付网络、交易平台、社交网络）。
  不算：分销网络、门店网络、合作伙伴网络、覆盖国家多——这些是渠道规模，不是网络效应。
- cost_advantage 成本优势：成本结构持续低于对手（规模采购、独特资源、工艺、地理位置）。
  不算：只说毛利率高（那可能是定价权，归无形资产）。
- efficient_scale 有效规模：市场容量只够少数几家盈利，新进入者进来会让所有人都不赚钱（如管道、机场、区域垄断）。
  不算：市场份额大、销量大。

强度：strong = 原文明确描述了该机制且是公司核心；moderate = 有明确描述但只覆盖部分业务；
weak = 只有间接迹象；none = 原文没有证据。拿不准时取较低的一档。

规则：
- 只依据给定的年报原文，不用你自己的背景知识补充。
- quotes 必须从原文逐字复制（英文，保留原标点），不能改写、翻译、省略或拼接；每条 20~300 字符。
- reason 用中文大白话写给普通投资者，不出现买入、卖出、推荐、看多、看空等字样。
- 五种来源都要给出判断，各一条。"""


_PUNCT = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-",
                        "\u2014": "-", "\u2011": "-", "\u00ad": None, "\u00a0": " "})


def _norm(s: str) -> str:
    """比对用：统一弯引号 / 破折号 / 软连字符，压缩空白，忽略大小写。"""
    return re.sub(r"\s+", " ", s.translate(_PUNCT)).strip().lower()


def _strip_wrapping(q: str) -> str:
    """模型常在引用两端加引号或省略号，比对前剥掉（不改动中间内容）。"""
    return q.strip().strip('"\'\u201c\u201d\u2018\u2019').strip().strip("…").strip(".").strip()


def verify_quotes(result: MoatSources, section: str) -> MoatSources:
    """只保留在原文里逐字出现的引用；某来源判了强度却没有任何可核实引用 → 降为 none。"""
    hay = _norm(section)
    for s in result.sources:
        s.raw_quotes = list(s.quotes)
        cleaned = [_strip_wrapping(q) for q in s.quotes]
        s.quotes = [q for q in cleaned if len(_norm(q)) >= 20 and _norm(q) in hay]
        if s.strength != "none" and not s.quotes:
            s.reason = f"（原判 {s.strength}，引用无法在年报中核实，作废）" + s.reason
            s.strength = "none"
    return result


RUNS = 3
_ORDER = ["none", "weak", "moderate", "strong"]


async def sources(section: str, symbol: str) -> MoatSources:
    """独立判断 RUNS 次，每种来源取强度中位数（模型温度为 0 也不确定，用多次投票压低波动）；
    理由与引用取自强度等于中位数的那一次。"""
    runs = [await _sources_once(section, symbol) for _ in range(RUNS)]
    merged: list[SourceJudgement] = []
    for key in SOURCE_ZH:
        picks = [next(s for s in r.sources if s.source == key) for r in runs]
        med = sorted(_ORDER.index(p.strength) for p in picks)[len(picks) // 2]
        chosen = next(p for p in picks if _ORDER.index(p.strength) == med)
        chosen.votes = [p.strength for p in picks]
        merged.append(chosen)
    return MoatSources(sources=merged, threats=runs[0].threats)


async def _sources_once(section: str, symbol: str) -> MoatSources:
    msgs = [SystemMessage(SYSTEM), HumanMessage(f"公司代码：{symbol}\n\n年报 Item 1（业务）原文：\n\n{section}")]
    last: Exception | None = None
    for _ in range(3):  # 模型偶发返回空结果 / 格式错，重试
        try:
            out = await llm_service.call(msgs, response_format=MoatSources, temperature=0)
        except Exception as e:  # noqa: BLE001
            last = e
            continue
        if out is not None and {x.source for x in out.sources} == set(SOURCE_ZH):
            return verify_quotes(out, section)
    raise RuntimeError(f"大模型 3 次都没给出有效结果：{last}")


# ---------------- 合成 ----------------

def rating(ev: dict, src: MoatSources) -> str:
    strong = sum(s.strength == "strong" for s in src.sources)
    moderate = sum(s.strength == "moderate" for s in src.sources)
    if ev["level"] == "strong" and (strong >= 1 or moderate >= 2):
        return "wide"
    if ev["level"] in ("strong", "moderate") and (strong + moderate) >= 1:
        return "narrow"
    return "none"


async def run(symbols: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        fmp = FmpClient(client, None, "batch")
        for sym in symbols:
            try:
                ev = await evidence(fmp, sym)
                biz = await tenk_business(client, sym)
                if biz is None:
                    print(f"{sym}: 未取到 10-K 业务章节", flush=True)
                    continue
                section, url = biz
                src = await sources(section, sym)
            except Exception as e:  # noqa: BLE001 校准脚本：单只失败继续
                print(f"{sym}: 失败 {type(e).__name__}: {e}", flush=True)
                continue
            r = rating(ev, src)
            texts = [s.reason for s in src.sources] + [src.threats]
            row = {"symbol": sym, "expected": EXPECTED.get(sym), "rating": r, "evidence": ev, "tenk_url": url,
                   "section_chars": len(section), "section": section, "sources": [s.model_dump() for s in src.sources],
                   "threats": src.threats, "forbidden": sorted({w for t in texts for w in contains_forbidden(t)})}
            rows.append(row)
            (OUT_DIR / f"{sym}.json").write_text(json.dumps(row, ensure_ascii=False, indent=1))
            srcs = " ".join(f"{SOURCE_ZH[s.source]}:{s.strength[0].upper()}({len(s.quotes)})" for s in src.sources)
            print(f"{sym:6} 参照={EXPECTED.get(sym) or '-':5} 结果={r:6} | 证据={ev['level']:8} "
                  f"ROIC>WACC {ev['years_above']}/{ev['n_years']} 平均超额 {ev['avg_spread']} 趋势 {ev['trend']} "
                  f"WACC {ev['wacc']} | {srcs}", flush=True)
    graded = [r for r in rows if r["expected"]]
    hit = sum(r["rating"] == r["expected"] or (r["expected"] == "wide" and r["rating"] == "narrow") for r in graded)
    exact = sum(r["rating"] == r["expected"] for r in graded)
    print(f"\n有参照 {len(graded)} 只：完全一致 {exact}，方向一致（宽判窄也算）{hit}")
    (OUT_DIR / "_summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1:] or [*EXPECTED, *EXTRA]))
