"""A 股 / 港股评级雷达的数据：A 股东财研报的本次 / 上次评级，港股经济通券商评级的逐日比对。"""
from datetime import date

from app.services.signal_radar import analyst_events as ae
from app.services.signal_radar import cnhk_analyst as ca


def _r(d, code, org, new, last, change=3):
    return {"publishDate": f"{d} 00:00:00.000", "stockCode": code, "orgSName": org,
            "emRatingName": new, "lastEmRatingName": last, "ratingChange": change}


def test_cn_reports_to_actions_only_tier_changes():
    """同一家券商本次与上次评级档位不同才算一次上调 / 下调；维持、首次覆盖、同档换说法都不算。"""
    rows = [
        _r("2026-10-08", "600519", "太平洋", "增持", "买入", 1),     # 下调
        _r("2026-10-07", "000001", "中信", "买入", "增持", 0),       # 上调
        _r("2026-10-06", "000001", "国金", "买入", "买入"),          # 维持
        _r("2026-10-05", "000002", "华泰", "买入", "", 2),           # 首次覆盖
        _r("2026-10-04", "000003", "某券商", "未知评级", "买入"),     # 未知评级不算
        _r("2026-10-03", "1234", "华泰", "增持", "买入"),            # 代码补齐 6 位
    ]
    out = ca.cn_actions_from_reports(rows)
    assert set(out) == {"600519", "000001", "001234"}
    assert out["600519"] == [{"date": "2026-10-08", "firm": "太平洋", "prev": "买入", "new": "增持", "action": "downgrade"}]
    assert out["000001"][0]["action"] == "upgrade" and len(out["000001"]) == 1


def test_cn_actions_sorted_new_to_old():
    rows = [_r("2026-10-01", "600000", "A", "增持", "买入"), _r("2026-10-09", "600000", "B", "买入", "增持")]
    assert [a["date"] for a in ca.cn_actions_from_reports(rows)["600000"]] == ["2026-10-09", "2026-10-01"]


def test_hk_diff_first_snapshot_records_state_only():
    """第一次看到某只股票只记状态、不出事件（没有「之前」可比）。"""
    state, events = ca.diff_hk_ratings({}, {"00700": {"美银": ("买入", "2026-10-08")}}, date(2026, 10, 11))
    assert state == {"00700": {"美银": "买入"}} and events == {}


def test_hk_diff_tier_change_is_an_event_dated_by_broker_update():
    """档位变了记一次（日期用券商的更新日期，太早或缺失就用当天）；同档换说法、新增券商只更新状态。"""
    prev = {"00700": {"美银": "买入", "瑞银": "持有", "花旗": "买入"}}
    cur = {"00700": {"美银": ("持有", "2026-10-09"),        # 下调
                     "瑞银": ("增持", None),                # 上调，没有更新日期 → 当天
                     "花旗": ("强烈买入", "2026-10-10"),     # 同档，不算
                     "野村": ("买入", "2026-10-10")}}       # 新增券商，不算
    state, events = ca.diff_hk_ratings(prev, cur, date(2026, 10, 11))
    assert state["00700"] == {"美银": "持有", "瑞银": "增持", "花旗": "强烈买入", "野村": "买入"}
    acts = {a["firm"]: a for a in events["00700"]}
    assert acts["美银"] == {"date": "2026-10-09", "firm": "美银", "prev": "买入", "new": "持有", "action": "downgrade"}
    assert acts["瑞银"]["action"] == "upgrade" and acts["瑞银"]["date"] == "2026-10-11"
    assert set(acts) == {"美银", "瑞银"}


def test_hk_diff_keeps_brokers_missing_today():
    """今天页面上没出现的券商不删（经济通偶尔少列几家），下次出现再比。"""
    state, _ = ca.diff_hk_ratings({"00700": {"美银": "买入"}}, {"00700": {"瑞银": ("买入", None)}}, date(2026, 10, 11))
    assert state["00700"] == {"美银": "买入", "瑞银": "买入"}


def test_merge_events_dedups_and_prunes_old():
    old = {"00700": [{"date": "2026-06-01", "firm": "A", "prev": "买入", "new": "持有", "action": "downgrade"},
                     {"date": "2026-10-01", "firm": "B", "prev": "持有", "new": "买入", "action": "upgrade"}]}
    new = {"00700": [{"date": "2026-10-01", "firm": "B", "prev": "持有", "new": "买入", "action": "upgrade"},
                     {"date": "2026-10-10", "firm": "C", "prev": "买入", "new": "持有", "action": "downgrade"}]}
    out = ca.merge_events(old, new, date(2026, 10, 11))
    assert [a["firm"] for a in out["00700"]] == ["C", "B"]       # 90 天前的丢掉，重复的只留一条，新到旧


def test_bucket_of_understands_chinese_tiers():
    """A 股 / 港股的中文评级也能归到 buy / hold / sell（买入、增持 → buy；中性、持有 → hold；减持、卖出 → sell）。"""
    assert [ae.bucket_of(x) for x in ("买入", "增持", "中性", "持有", "减持", "卖出")] == [
        "buy", "buy", "hold", "hold", "sell", "sell"]


async def test_cnhk_radar_uses_same_rules_and_reports_market_total(monkeypatch):
    """A 股评级雷达：股票池里的按美股同一套规则出条目；market_actions 是全市场近 30 天的动作数。"""
    from app.services.signal_radar import analyst_radar as ar

    as_of = date(2026, 10, 11)
    acts = {"600519": [{"date": "2026-10-09", "firm": "太平洋", "prev": "增持", "new": "买入", "action": "upgrade"}],
            "000002": [{"date": "2026-10-01", "firm": "华泰", "prev": "买入", "new": "增持", "action": "downgrade"}],
            "000003": [{"date": "2026-08-01", "firm": "中信", "prev": "买入", "new": "中性", "action": "downgrade"}]}

    async def fake_actions(market, redis, day):
        return acts, None

    async def fake_tags(market, redis):
        return {}

    async def fake_grades(market, pairs, end):
        return {}

    monkeypatch.setattr(ca, "actions_for", fake_actions)
    monkeypatch.setattr(ca, "today_local", lambda: as_of)
    monkeypatch.setattr(ar.sectors, "load_sector_tags", fake_tags)
    monkeypatch.setattr(ar, "_grades_for", fake_grades)
    out = await ar.analyst_radar("cn", [("600519", "贵州茅台"), ("000001", "平安银行")], "csi300", redis=None)  # type: ignore[arg-type]
    assert out.supported and [(i.symbol, i.kind, i.ring_days) for i in out.items] == [("600519", "analyst_up", 3)]
    assert out.items[0].analyst.from_bucket == "buy" and out.items[0].analyst.from_grade == "增持"
    assert out.market_actions == 2        # 08-01 那次超出 30 天
