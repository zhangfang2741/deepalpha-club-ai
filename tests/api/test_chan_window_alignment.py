"""雷达与详情页的日线取数区间必须一致，且详情页始终带预热。

czsc 要积累若干笔（一买 >=5、三买 >=7、二买 >=15）才开始出信号：详情页若不预热，
图表开头一两个月会一个买卖点都没有。iOS 从雷达点进详情时传 start=as_of-270、
warmup_days=0（为与雷达同区间）；服务端忽略 warmup_days、始终预热 180 天，
雷达则把取数起点同步前移 180 天，两边拿到的 K 线区间完全相同。
"""
from datetime import date, timedelta

from app.api.v1.chan import _anchor_start
from app.services.signal_radar import service as radar


def test_detail_always_warms_up_even_when_client_sends_zero():
    assert _anchor_start("2026-01-01", "daily", 0) == "2025-07-05"
    assert _anchor_start("2026-01-01", "daily", None) == "2025-07-05"


def test_radar_fetch_range_equals_detail_range_from_radar_entry():
    as_of = date(2026, 9, 24)
    detail_visible_start = (as_of - timedelta(days=270)).isoformat()  # iOS openSymbol 的 start
    assert radar._fetch_start(as_of, window=45) == _anchor_start(detail_visible_start, "daily", 0)
