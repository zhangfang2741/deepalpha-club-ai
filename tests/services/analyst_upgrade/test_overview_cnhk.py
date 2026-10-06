"""A 股 / 港股分析师评级概览：五档名称、官方评级统计、评级变动动作、目标价门槛、港股无历史。"""

import json
from datetime import date
from pathlib import Path

from app.services.analyst_upgrade.overview_cnhk import build_cn_overview, build_hk_overview, cn_rating_stats
from app.services.quant_research.cnhk import etnet
from app.services.quant_research.cnhk.ratings import tier
from app.services.quant_research.copy import contains_forbidden

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "quant_research" / "cnhk"
TODAY = date(2026, 10, 3)


def _rep(d, org, em, last="", raw=None, target=""):
    return {"publishDate": f"{d} 00:00:00.000", "orgSName": org, "emRatingName": em, "lastEmRatingName": last,
            "sRatingName": raw or em, "indvAimPriceT": target}


def test_official_stats_used_for_distribution():
    f10 = json.loads((FIX / "f10_600519.json").read_text())
    r = cn_rating_stats(f10, TODAY, "zh")
    assert (r.current.strong_buy, r.current.buy, r.current.total) == (34, 9, 43)
    assert r.bucket_labels == ["买入", "增持", "中性", "减持", "卖出"]
    o = build_cn_overview("600519", "zh", TODAY, [_rep("2026-09-21", "诚通证券", "买入", "买入", "强烈推荐")], 1258.6, f10)
    assert o.status == "ok" and o.ratings.current.total == 43
    g = o.recent_grades[0]
    assert g.new_grade_label == "强烈推荐" and g.action == "maintain"  # 中文引述券商原文


def test_cn_actions_and_previous_from_same_org():
    reps = [_rep("2026-09-01", "甲证券", "买入", "增持"), _rep("2026-06-01", "甲证券", "增持", "", raw="谨慎推荐"),
            _rep("2026-08-01", "乙证券", "中性", "买入"), _rep("2026-07-01", "丙证券", "买入", "")]
    o = build_cn_overview("000001", "zh", TODAY, reps, 10.0)
    by = {(g.firm, g.date): g for g in o.recent_grades}
    up = by[("甲证券", "2026-09-01")]
    assert up.action == "upgrade" and up.previous_grade_label == "谨慎推荐"
    assert by[("乙证券", "2026-08-01")].action == "downgrade"
    assert by[("丙证券", "2026-07-01")].action == "init"
    # 没有官方统计时按研报列表重建：每家机构取近 6 个月最近一次（甲=买入、乙=中性、丙=买入）
    cur = o.ratings.current
    assert (cur.strong_buy, cur.hold, cur.total) == (2, 1, 3)
    en = build_cn_overview("000001", "en", TODAY, reps, 10.0)
    assert en.recent_grades[0].new_grade_label == "Buy" and en.ratings.bucket_labels[1] == "Outperform"


def test_cn_target_needs_three_institutions():
    two = [_rep("2026-09-01", "甲", "买入", target="20"), _rep("2026-08-01", "乙", "买入", target="22")]
    assert build_cn_overview("000001", "zh", TODAY, two, 10.0).price_target is None
    three = two + [_rep("2026-07-01", "丙", "增持", target="30.5"), _rep("2025-01-01", "丁", "买入", target="99")]
    t = build_cn_overview("000001", "zh", TODAY, three, 10.0).price_target
    assert (t.low, t.median, t.high) == (20.0, 22.0, 30.5) and t.vs_price_pct == 120.0  # 一年半前的不算


def test_hk_overview_from_etnet():
    fc = etnet.parse((FIX / "etnet_00700.html").read_text())
    o = build_hk_overview("00700", "zh", TODAY, fc, 421.2)
    assert o.status == "ok" and o.ratings.history == [o.ratings.current] and o.ratings.change_text is None
    assert o.ratings.current.total >= 10 and o.recent_grades_title == "各券商最新评级"
    assert all(g.action == "latest" and g.previous_grade is None for g in o.recent_grades)
    assert o.price_target.low <= o.price_target.median <= o.price_target.high
    assert o.recent_grades[0].price_target is not None


def test_empty_and_unknown_ratings():
    assert build_cn_overview("000001", "zh", TODAY, [], None).status == "insufficient_data"
    assert build_hk_overview("00001", "zh", TODAY, None, None).status == "insufficient_data"
    assert tier("优于大市") == 1 and tier("大市同步") == 2 and tier("某种没见过的评级") is None


def test_our_copy_has_no_forbidden_words():
    fc = etnet.parse((FIX / "etnet_00005.html").read_text())
    for o in (build_hk_overview("00005", "zh", TODAY, fc, 149.5), build_hk_overview("00005", "en", TODAY, fc, 149.5)):
        ours = [o.note, o.recent_grades_title, o.price_target.vs_price_text] + [g.action_label for g in o.recent_grades]
        assert all(contains_forbidden(t) == [] for t in ours if t), ours


def test_hk_related_news_filters_rating_titles():
    from app.services.analyst_upgrade.overview_cnhk import build_hk_related_news

    rows = [{"Art_Title": "大摩：腾讯获“增持”评级", "Art_Url": "http://x/a", "Art_ShowTime": "2026-09-29 10:00:00", "Art_MediaName": "A"},
            {"Art_Title": "南向资金净买入腾讯控股14亿港元", "Art_Url": "http://x/b", "Art_ShowTime": "2026-09-30 10:00:00"},
            {"Art_Title": "花旗看好微信", "Art_Url": "javascript:1", "Art_ShowTime": "2026-09-25 10:00:00"},
            {"Art_Title": "腾讯回购股份", "Art_Url": "http://x/c", "Art_ShowTime": "2026-09-24 10:00:00"}]
    out = build_hk_related_news(rows)
    assert [n.url for n in out] == ["http://x/a"] and out[0].date == "2026-09-29"
