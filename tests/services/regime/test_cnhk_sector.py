"""A 股 / 港股行业状态：选成分股、合成行业指数、对齐、整条计算（纯函数，不联网不连库）。"""
from datetime import date, timedelta
from types import SimpleNamespace as NS

import numpy as np
import pytest

from app.services.regime import cnhk_sector as cs
from app.services.regime.cnhk import MARKET_CONFIGS
from app.services.regime.sector_pipeline import compute_sector_regimes


def _days(n: int, start: date = date(2023, 1, 2)) -> list[str]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bars(days: list[str], seed: int, drift: float = 0.0004, vol: float = 0.012) -> list[dict]:
    rng = np.random.default_rng(seed)
    close = 10 * np.cumprod(1 + rng.normal(drift, vol, len(days)))
    return [{"time": d, "open": c, "high": c * 1.01, "low": c * 0.99, "close": float(c), "volume": 1e6}
            for d, c in zip(days, close, strict=True)]


def test_pick_constituents_cn_takes_top_market_cap_per_sw_sector_and_skips_st():
    meta = {
        "600519": NS(industry="白酒Ⅱ", market_cap=2e12, name="贵州茅台"),
        "000858": NS(industry="白酒Ⅱ", market_cap=7e11, name="五粮液"),
        "000568": NS(industry="白酒Ⅱ", market_cap=3e11, name="泸州老窖"),
        "600000": NS(industry="白酒Ⅱ", market_cap=9e12, name="ST某某"),       # ST：剔除
        "601398": NS(industry="银行Ⅱ", market_cap=2e12, name="工商银行"),
        "000001": NS(industry="没见过的行业", market_cap=1e12, name="某某"),    # 未映射：没有标签
        "300001": NS(industry="银行Ⅱ", market_cap=None, name="无市值"),          # 无市值：剔除
    }
    picks = cs.pick_constituents("cn", meta, top_n=2)
    assert picks["食品饮料"] == ["600519.SS", "000858.SZ"]
    assert picks["银行"] == ["601398.SS"]
    assert set(picks) == {"食品饮料", "银行"}


def test_pick_constituents_hk_uses_hang_seng_sectors_and_skips_rmb_counter():
    meta = {
        "00700": NS(industry="软件服务", market_cap=4e12, name="腾讯控股"),
        "00981": NS(industry="半导体", market_cap=1e11, name="中芯国际"),
        "80700": NS(industry="软件服务", market_cap=4e12, name="腾讯控股-R"),    # 人民币柜台：剔除
        "00939": NS(industry="银行", market_cap=1e12, name="建设银行"),
    }
    picks = cs.pick_constituents("hk", meta, top_n=5)
    assert picks == {"资讯科技业": ["0700.HK", "0981.HK"], "金融业": ["0939.HK"]}


def test_sector_index_is_equal_weight_of_daily_returns():
    days = _days(5)

    def flat(growth: float) -> list[dict]:
        c = 100.0
        out = []
        for d in days:
            out.append({"time": d, "open": c, "high": c, "low": c, "close": c, "volume": 10.0})
            c *= 1 + growth
        return out

    idx = cs.build_sector_index([flat(0.10), flat(0.00), flat(0.02)], days)
    assert idx is not None
    # 第 2 天起每天指数涨 (10% + 0% + 2%) / 3 = 4%
    assert idx["close"][0] == pytest.approx(1.0)
    assert idx["close"][1] == pytest.approx(1.04)
    assert idx["close"][2] == pytest.approx(1.04 ** 2)
    assert idx["volume"][1] > 0


def test_sector_index_handles_late_listing_and_too_few_constituents():
    days = _days(30)
    full = _bars(days, 1)
    late = _bars(days[15:], 2)               # 后一半才有数据
    idx = cs.build_sector_index([full, full, late], days)
    assert idx is not None and np.isfinite(idx["close"]).all()
    assert cs.build_sector_index([full, full], days) is None   # 不足 MIN_CONSTITUENTS 只
    assert cs.build_sector_index([full, full, []], days) is None


def test_build_sector_market_data_and_compute_end_to_end():
    market = "cn"
    days = _days(700)
    bench = _bars(days, 99, vol=0.01)
    constituents = {
        "银行": {f"B{i}": _bars(days, 10 + i, drift=0.0006) for i in range(4)},
        "煤炭": {f"C{i}": _bars(days, 20 + i, drift=-0.0003) for i in range(4)},
        "太少": {"X": _bars(days, 30)},
    }
    data = cs.build_sector_market_data(market, bench, constituents)
    assert set(data.sectors) == {"银行", "煤炭"} and len(data.dates) == 700
    res = compute_sector_regimes(data)
    for sector, recs in res.items():
        fit = [r for r in recs if r.p_risk_on is not None]
        assert fit, sector
        last = fit[-1]
        assert last.rs_vs_market is not None
        assert abs(last.p_risk_on + last.p_neutral + last.p_risk_off - 1) < 1e-6
    assert MARKET_CONFIGS[market].benchmark


def test_build_sector_market_data_requires_benchmark_and_constituents():
    with pytest.raises(RuntimeError, match="基准"):
        cs.build_sector_market_data("cn", [], {"银行": {}})
    with pytest.raises(RuntimeError, match="成分股"):
        cs.build_sector_market_data("cn", _bars(_days(100), 1), {"银行": {"B": []}})
