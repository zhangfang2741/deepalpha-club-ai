"""验证所有指标、旧缓存与英文响应的教育文案契约。"""

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from app.schemas.quant_research import QuantResearchOut
from app.services.quant_research.builder import build_payload, evaluate
from app.services.quant_research.education import enrich_education, metric_interpretation
from app.services.quant_research.metrics import METRICS
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
