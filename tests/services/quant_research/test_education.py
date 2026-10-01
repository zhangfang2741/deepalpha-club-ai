"""验证所有指标、旧缓存与英文响应的教育文案契约。"""

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from app.schemas.quant_research import QuantResearchOut
from app.services.quant_research.builder import build_payload, evaluate
from app.services.quant_research.copy import contains_forbidden
from app.services.quant_research.education import enrich_education, metric_interpretation
from app.services.quant_research.glossary import input_hint
from app.services.quant_research.metrics import INPUT_LABELS, METRICS
from tests.services.quant_research.fixtures import FIXTURE_DIR, load_inputs


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_all_metrics_have_standalone_guidance(lang: str) -> None:
    for metric in METRICS.values():
        guidance = metric_interpretation(metric, lang)
        assert guidance.what and guidance.role and guidance.threshold and guidance.calculation
        assert "上一条" not in guidance.what
        if lang == "en":
            assert not any("\u4e00" <= char <= "\u9fff" for char in guidance.model_dump_json())


def test_legacy_payload_enrichment_preserves_research() -> None:
    raw = json.loads((FIXTURE_DIR / "golden_NVDA.json").read_text())
    for dimension in raw["dimensions"]:
        for group in dimension["groups"]:
            for metric in group["metrics"]:
                metric.pop("interpretation", None)
    payload = QuantResearchOut.model_validate(raw)
    enriched = enrich_education(payload, "zh").model_dump(mode="json")
    for dimension in enriched["dimensions"]:
        for group in dimension["groups"]:
            for metric in group["metrics"]:
                assert metric.pop("interpretation")["role"]
    assert enriched == raw


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_all_metrics_have_plain_language_explanation(lang: str) -> None:
    """每项指标都要有全称、大白话释义和高低怎么看，且不出现买卖导向词。"""
    for metric in METRICS.values():
        guidance = metric_interpretation(metric, lang)
        assert guidance.full_name and guidance.plain and guidance.reading, metric.key
        for text in (guidance.full_name, guidance.plain, guidance.reading):
            assert not contains_forbidden(text), (metric.key, text)
            if lang == "en":
                assert not any("一" <= char <= "鿿" for char in text), (metric.key, text)
        # 大白话不能退化成计算口径本身
        assert guidance.plain != guidance.what


def test_plain_language_reads_like_everyday_words() -> None:
    roe = metric_interpretation(METRICS["roe"], "zh")
    assert "净资产收益率" in roe.full_name
    assert "100 元" in roe.plain
    pe_fwd = metric_interpretation(METRICS["pe_fwd"], "zh")
    assert "预期" in pe_fwd.plain  # 前瞻口径要说明数字来自预期
    r6m = metric_interpretation(METRICS["r6m"], "zh")
    assert "6 个月" in r6m.plain


@pytest.mark.parametrize("key, required", [
    ("r3m", ["63", "÷", "− 1", "100%"]),
    ("r12m", ["252", "÷", "− 1", "100%"]),
    ("eps_fy1_90d", ["90", "|", "同一财年", "100%"]),
    ("rev_cagr3", ["3 年前", "^(1/3)", "100%"]),
    ("peg_fwd", ["下一财年", "本财年", "20% 取 20"]),
    ("rev_fwd", ["本财年", "上一财年", "100%"]),
])
def test_formula_preserves_periods_and_units(key: str, required: list[str]) -> None:
    calculation = metric_interpretation(METRICS[key], "zh").calculation
    assert calculation is not None
    assert all(part in calculation for part in required)


def test_quant_views_have_english_translations() -> None:
    root = Path(__file__).resolve().parents[3]
    resources = root / "ios/DeepAlphaChan/Resources/en.lproj/Localizable.strings"
    keys = set(re.findall(r'^"((?:\\.|[^"\\])*)"\s*=', resources.read_text(), re.MULTILINE))
    views = root / "ios/DeepAlphaChan/Views/Quant"
    paths = list(views.glob("*.swift")) + [root / "ios/DeepAlphaChan/Models/QuantLifecycleStage.swift"]
    for path in paths:
        used = set(re.findall(r'L\("((?:\\.|[^"\\])*)"', path.read_text()))
        assert used <= keys, f"{path.name} 缺少英文翻译：{used - keys}"



@pytest.mark.parametrize("lang", ["zh", "en"])
def test_missing_data_keeps_symbolic_formulas_without_fake_results(lang: str) -> None:
    inputs = replace(load_inputs("NVDA"), closes=[], estimates=[])
    payload = build_payload(evaluate(inputs, [], {}), lang, in_universe=True, sector_sample=0)
    metrics = {metric.key: metric for dim in payload.dimensions for group in dim.groups for metric in group.metrics}
    for key in ("r3m", "r12m", "eps_fy1_90d"):
        metric = metrics[key]
        assert metric.value is None and metric.formula is None
        assert metric.interpretation and metric.interpretation.calculation
        assert "÷" in metric.interpretation.calculation


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_every_formula_input_has_plain_hint(lang: str) -> None:
    """算式里每个输入项都能点开看大白话：这是什么 + 取的哪个期间。"""
    for name in INPUT_LABELS:
        hint = input_hint(name, lang)
        assert hint, name
        assert not contains_forbidden(hint), (name, hint)
        if lang == "en":
            assert not any("一" <= char <= "鿿" for char in hint), (name, hint)
    assert "未来 12 个月" in (input_hint("eps_ntm", "zh") or "")
    assert "再往前 12 个月" in (input_hint("rev_ttm_prev", "zh") or "")


def test_legacy_payload_gets_input_hints() -> None:
    raw = json.loads((FIXTURE_DIR / "golden_NVDA.json").read_text())
    for dimension in raw["dimensions"]:
        for group in dimension["groups"]:
            for metric in group["metrics"]:
                for item in (metric.get("formula") or {}).get("inputs", []):
                    item.pop("hint", None)
    enriched = enrich_education(QuantResearchOut.model_validate(raw), "zh")
    inputs = [i for d in enriched.dimensions for g in d.groups for m in g.metrics if m.formula for i in m.formula.inputs]
    assert inputs and all(i.hint for i in inputs)


def test_ios_grade_scale_matches_backend() -> None:
    """iOS「等级怎么来的」气泡里的分档 / 防抖 / 封顶常量必须与后端一致，否则解释会和真实等级对不上。"""
    from app.services.quant_research.grading import BANDS, HYSTERESIS
    from app.services.quant_research.scoring import CAP_CEILING, CAP_THRESHOLD, MIN_SAMPLE

    root = Path(__file__).resolve().parents[3]
    src = (root / "ios/DeepAlphaChan/Views/Quant/QuantExplain.swift").read_text()
    bands = [(float(lo), g) for lo, g in re.findall(r'\((\d+), "([A-F][+-]?)"\)', src)]
    assert bands == [(float(lo), g) for lo, g in BANDS]
    assert re.search(rf"hysteresis: Double = {HYSTERESIS:g}\b", src)
    assert re.search(rf"capThreshold: Double = {CAP_THRESHOLD:g}\b", src)
    assert f'capCeiling = "{CAP_CEILING}"' in src
    assert re.search(rf"minSample = {MIN_SAMPLE}\b", src)


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_every_metric_explains_why_and_purpose(lang: str) -> None:
    """每项指标都要讲清：为什么重要、我们为什么选它（在评级里的作用）。"""
    for metric in METRICS.values():
        g = metric_interpretation(metric, lang)
        assert g.why and g.purpose, metric.key
        assert g.why != g.plain and g.purpose != g.why
        for text in (g.why, g.purpose):
            assert not contains_forbidden(text), (metric.key, text)
            if lang == "en":
                assert not any("一" <= char <= "鿿" for char in text), (metric.key, text)
    gross = metric_interpretation(METRICS["gross_m"], "zh")
    assert "卖上价钱" in gross.why
    assert "盈利能力" in gross.purpose
