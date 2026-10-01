"""全流程：fixture 输入 + 真实板块分布（2026-09-30）→ 响应。golden 快照首次生成后人工核对再提交。"""

import json
import os
from datetime import timedelta

import pytest

from app.services.quant_research.builder import build_payload, evaluate, finalize_overall, grades_of
from app.services.quant_research.copy import contains_forbidden
from app.services.quant_research.revisions import EstimatePoint
from tests.services.quant_research.fixtures import FIXTURE_DIR, load_inputs

SYMBOLS = ["NVDA", "JPM", "O", "XOM"]


def _dists():
    raw = json.loads((FIXTURE_DIR / "distributions.json").read_text())
    return {tuple(k.split("|")): v for k, v in raw.items()}


def _run(sym, history=None, prev=None, extra_dists=None):
    d = _dists() | (extra_dists or {})
    ev = evaluate(load_inputs(sym), history or [], d, prev)
    finalize_overall(ev, d[("_all", "_overall")], prev)
    return ev


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


@pytest.mark.parametrize("sym", SYMBOLS)
@pytest.mark.parametrize("lang", ["zh", "en"])
def test_payload_has_no_forbidden_words(sym, lang):
    payload = build_payload(_run(sym), lang, in_universe=True, sector_sample=100).model_dump()
    bad = [(s, contains_forbidden(s)) for s in _strings(payload) if contains_forbidden(s)]
    assert bad == []


def test_nvda_structure():
    ev = _run("NVDA")
    p = build_payload(ev, "zh", in_universe=True, sector_sample=191)
    assert [d.key for d in p.dimensions] == ["valuation", "growth", "profitability", "momentum", "revisions", "moat"]
    moat = p.dimensions[-1]
    assert moat.counts_in_overall is False
    # fixture 的板块分布（2026-09-30）早于护城河，没有它的分档 → 数值算出、但暂不评级
    assert all(m.value is not None for g in moat.groups for m in g.metrics)
    assert all(d.counts_in_overall for d in p.dimensions[:-1])
    rev = p.dimensions[4]
    assert rev.status == "accumulating" and rev.status_note == "修正历史积累中（已 0 天）"
    assert p.overall.dimensions_used == 4
    assert p.overall.note == "本次综合等级基于 4 个维度"
    val = p.dimensions[0]
    assert val.formula and val.formula.endswith(f"→ {val.grade}")
    pe_fwd = next(m for g in val.groups for m in g.metrics if m.key == "pe_fwd")
    assert pe_fwd.formula.expression.startswith("股价 ")
    assert pe_fwd.formula.inputs[0].note == ev.inp.price_date
    assert "位分析师均值" in pe_fwd.formula.inputs[1].note
    assert p.peer_group.text == "与信息技术板块 191 家公司比"
    assert p.stage.key == "growth" and p.stage.revenue_growth_pct is not None
    assert sum(d.is_highest for d in p.dimensions) == 1 and sum(d.is_lowest for d in p.dimensions) == 1


def test_revisions_with_history():
    inp = load_inputs("NVDA")
    fy1 = inp.fy1["date"]
    hist = [EstimatePoint(inp.as_of - timedelta(days=100 - i), fy1, 9.0 + i * 0.003, 3e11, 30) for i in range(101)]
    # 种子分布里没有修正类指标（当时还没有快照历史），补一份合成的板块分布
    synth = {("information_technology", k): [i / 1000 for i in range(-50, 50)]
             for k in ("eps_fy1_30d", "eps_fy1_90d", "eps_fy2_90d", "rev_fy1_90d")}
    ev = _run("NVDA", history=hist, extra_dists=synth)
    rev = next(d for d in ev.dims if d.key == "revisions")
    # 只有 FY1 的 EPS 两项 + 营收一项有历史；FY2 缺 → 3/4 参与
    assert rev.status == "ok"
    assert ev.metrics["eps_fy1_90d"].value > 0


def test_grades_roundtrip_hysteresis():
    ev = _run("NVDA")
    g = grades_of(ev)
    assert g["overall"] == ev.overall.grade
    ev2 = _run("NVDA", prev=g)
    assert grades_of(ev2) == g


def test_jpm_has_no_stage_and_notes():
    p = build_payload(_run("JPM"), "zh", in_universe=True, sector_sample=100)
    assert p.stage is None
    rev_fwd = next(m for d in p.dimensions for g in d.groups for m in g.metrics if m.key == "rev_fwd")
    assert rev_fwd.status == "not_applicable" and "口径不同" in rev_fwd.status_note


@pytest.mark.parametrize("sym", SYMBOLS)
def test_golden(sym):
    path = FIXTURE_DIR / f"golden_{sym}.json"
    got = build_payload(_run(sym), "zh", in_universe=True, sector_sample=100).model_dump(mode="json")
    if os.environ.get("UPDATE_GOLDEN") or not path.exists():
        path.write_text(json.dumps(got, ensure_ascii=False, indent=1))
        pytest.skip(f"golden 已生成：{path.name}，人工核对后提交")
    assert got == json.loads(path.read_text())
