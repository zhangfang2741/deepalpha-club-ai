"""护城河来源：引用核对、投票合并、输出校验、格式兜底（不调用大模型）。"""

import json

from app.services.quant_research.moat.sources import (
    SOURCE_KEYS,
    MoatJudgement,
    _valid,
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
    assert _valid(_j(["none"] * 5))
    dup = _j(["none"] * 5)
    dup.sources[1].source = "intangible_assets"
    assert not _valid(dup)
    assert not _valid(_j(["none"] * 5, reason_en="Investors should buy this stock."))
    assert not _valid(_j(["none"] * 5, threats_en="竞争加剧"))


def test_coerces_stringified_lists_from_model():
    raw = {"sources": json.dumps([{"source": k, "strength": "weak", "reason_zh": "z", "reason_en": "e",
                                   "quotes": "single quote string here ok"} for k in SOURCE_KEYS]),
           "threats_zh": "威胁", "threats_en": "threats"}
    j = MoatJudgement.model_validate(raw)
    assert len(j.sources) == 5 and j.sources[0].quotes == ["single quote string here ok"]
