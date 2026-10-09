"""用户自定义指标参数（App「指标设置」）：/chan/analysis 的 ma / ema / boll 查询参数。

不传 = 与以前完全一样（旧版 App 不受影响）；传了非法值不报错、回退默认（App 画图不因参数出错而空白）。
"""
from app.services.chan.analyzer import ChanAnalyzer
from app.services.chan.indicators import (
    BOLL_MULT,
    BOLL_PERIOD,
    EMA_PERIODS,
    IndicatorParams,
    parse_boll,
    parse_periods,
)


def _bars(n=80):
    return [{"time": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 10 + i % 5, "high": 11 + i % 5,
             "low": 9 + i % 5, "close": 10.5 + i % 5, "volume": 1.0} for i in range(n)]


def test_parse_periods_valid_sorted_dedup():
    assert parse_periods("60,5,20,5", max_count=3) == (5, 20, 60)


def test_parse_periods_none_or_empty_means_default():
    assert parse_periods(None, max_count=3) is None
    assert parse_periods("", max_count=3) is None


def test_parse_periods_invalid_falls_back():
    assert parse_periods("5,abc", max_count=3) is None
    assert parse_periods("1,5", max_count=3) is None  # 周期至少 2
    assert parse_periods("5,999", max_count=3) is None  # 超过上限
    assert parse_periods("5,10,20,60", max_count=3) is None  # 线太多（App 只有 3 种颜色）


def test_parse_boll():
    assert parse_boll("26,2.5") == (26, 2.5)
    assert parse_boll(None) is None
    assert parse_boll("20") is None
    assert parse_boll("20,0") is None
    assert parse_boll("20,9") is None
    assert parse_boll("1,2") is None


def test_analyze_default_params_unchanged():
    r = ChanAnalyzer().analyze("TEST", _bars())
    assert r.ma is not None and r.ma.periods == (5, 20, 60)
    assert r.ema is not None and r.ema.periods == EMA_PERIODS
    assert r.boll is not None and (r.boll.period, r.boll.mult) == (BOLL_PERIOD, BOLL_MULT)


def test_analyze_custom_params():
    params = IndicatorParams(ma=(10, 30), ema=(5, 10), boll=(26, 2.5))
    r = ChanAnalyzer().analyze("TEST", _bars(), indicator_params=params)
    assert r.ma is not None and r.ma.periods == (10, 30)
    assert r.ema is not None and r.ema.periods == (5, 10)
    assert r.boll is not None and (r.boll.period, r.boll.mult) == (26, 2.5)


def test_custom_ma_overrides_weekly_default():
    params = IndicatorParams(ma=(7,))
    r = ChanAnalyzer().analyze("TEST", _bars(), freq="weekly", indicator_params=params)
    assert r.ma is not None and r.ma.periods == (7,)
