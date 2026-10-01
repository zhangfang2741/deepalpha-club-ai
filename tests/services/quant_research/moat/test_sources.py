"""护城河来源：引用核对、投票合并、输出校验、格式兜底（不调用大模型）。"""

import json

from app.services.quant_research.moat.sources import (
    SOURCE_KEYS,
    MoatJudgement,
    invalid_reason,
    merge_votes,
    verify_quotes,
)

SECTION = "Our network connects 175 million merchants worldwide. The world’s largest brands rely on us — every day."


def _j(strengths, quotes=None, reason_en="Plain reason.", threats_en="Competition."):
    return MoatJudgement(
        sources=[{"source": k, "strength": s, "reason_zh": "理由", "reason_en": reason_en,
                  "quotes": (quotes or {}).get(k, [])} for k, s in zip(SOURCE_KEYS, strengths, strict=True)],
        threats_zh="威胁", threats_en=threats_en)


def test_quotes_verified_verbatim_with_punctuation_normalized():
    j = _j(["strong", "moderate", "strong", "none", "none"], quotes={
        "intangible_assets": ['"The world\'s largest brands rely on us - every day."'],  # 直引号 / 两端引号 / 破折号
        "switching_costs": ["We have very high switching costs for customers."],          # 原文没有 → 作废
        "network_effect": ["Our network connects 175 million merchants worldwide"],
    })
    out = verify_quotes(j, SECTION)
    by = {s.source: s for s in out.sources}
    assert by["intangible_assets"].strength == "strong" and len(by["intangible_assets"].quotes) == 1
    assert by["switching_costs"].strength == "none" and by["switching_costs"].quotes == []
    assert by["network_effect"].strength == "strong"


def test_merge_takes_median_strength_per_source():
    runs = [_j(["strong", "none", "weak", "moderate", "none"]),
            _j(["moderate", "none", "strong", "moderate", "weak"]),
            _j(["strong", "weak", "none", "none", "strong"])]
    merged = merge_votes(runs)
    assert [s.strength for s in merged.sources] == ["strong", "none", "weak", "moderate", "weak"]


def test_invalid_when_missing_source_forbidden_words_or_chinese_in_english():
    assert invalid_reason(_j(["none"] * 5)) is None
    dup = _j(["none"] * 5)
    dup.sources[1].source = "intangible_assets"
    assert invalid_reason(dup).startswith("sources=")
    assert invalid_reason(_j(["none"] * 5, reason_en="We recommend this stock.")) == "forbidden=['recommend']"
    assert invalid_reason(_j(["none"] * 5, threats_en="竞争加剧")) == "chinese_in_english"


def test_coerces_stringified_lists_from_model():
    raw = {"sources": json.dumps([{"source": k, "strength": "weak", "reason_zh": "z", "reason_en": "e",
                                   "quotes": "single quote string here ok"} for k in SOURCE_KEYS]),
           "threats_zh": "威胁", "threats_en": "threats"}
    j = MoatJudgement.model_validate(raw)
    assert len(j.sources) == 5 and j.sources[0].quotes == ["single quote string here ok"]


def test_descriptive_trade_words_are_neutralized_not_rejected():
    """理由里「能以高价 sell」这类描述生意的用法换成中性词，不让整只股票判断失败；数据商名仍然拒绝。"""
    from app.services.quant_research.moat.sources import invalid_reason, neutralize

    j = _j(["none"] * 5, reason_en="Its brand lets it sell at premium prices; customers buy repeatedly.")
    j.sources[0].reason_zh = "公司能以高价卖出产品，客户反复买入。"
    neutralize(j)
    assert invalid_reason(j) is None
    assert "sell" not in j.sources[0].reason_en.lower().split()
    assert "卖出" not in j.sources[0].reason_zh
    bad = _j(["none"] * 5, reason_en="Data from FMP shows high margins.")
    neutralize(bad)
    assert invalid_reason(bad) and "FMP" in invalid_reason(bad)


async def test_rate_limit_triggers_global_cooldown(monkeypatch):
    """遇到 429 全局冷却：后续调用先等冷却结束，不立刻重试加压（大模型套餐与 App 其它功能共用）。"""
    from app.services.quant_research.moat import sources

    class RateLimitError(Exception):
        pass

    calls, sleeps = [], []
    good = _j(["none"] * 5)

    async def fake_call(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise RateLimitError("Error code: 429 - rate_limit_error")
        return good

    async def fake_sleep(sec):
        sleeps.append(sec)

    monkeypatch.setattr(sources, "_cooldown_until", 0.0)
    monkeypatch.setattr(sources.llm_service, "call", fake_call)
    monkeypatch.setattr(sources.asyncio, "sleep", fake_sleep)
    out = await sources.judge_once("x" * 100, "TEST")
    assert len(calls) == 2 and out is good
    assert sleeps and sleeps[0] > 60  # 第二次调用前等了冷却


async def test_quota_exhausted_is_raised_immediately_without_retries(monkeypatch):
    import pytest

    from app.services.quant_research.moat import sources

    calls = []

    async def fake_call(*a, **k):
        calls.append(1)
        raise RuntimeError("Error code: 429 - 已达到 Token Plan 用量上限：请升级 Token Plan 套餐 (2056)")

    monkeypatch.setattr(sources.llm_service, "call", fake_call)
    with pytest.raises(sources.QuotaExhausted):
        await sources.judge_once("x" * 100, "TEST")
    assert len(calls) == 1


def test_company_name_with_trade_word_is_not_forbidden_or_rewritten():
    """百思买（Best Buy）的公司名里有 buy：既不能判违规，也不能被替换成 Best Purchase。"""
    from app.services.quant_research.moat.sources import invalid_reason, neutralize

    j = _j(["none"] * 5, reason_en="Best Buy has a strong brand; it can sell services.")
    j.sources[0].reason_zh = "Best Buy 的品牌认知度高。"
    neutralize(j, names=["Best Buy", "Best Buy Co., Inc."])
    assert invalid_reason(j, names=["Best Buy"]) is None
    assert j.sources[0].reason_en.startswith("Best Buy has") and "offer services" in j.sources[0].reason_en
    assert j.sources[0].reason_zh.startswith("Best Buy")
