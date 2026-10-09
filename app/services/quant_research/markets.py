"""各市场的口径差异：比较样本的叫法、缺数据源而不展示的指标、是否有护城河。

打分规则（百分位、分档、防抖、一票否决）三个市场完全一致，这里只放「数据有没有」和「怎么称呼样本」。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketProfile:
    key: str
    universe_zh: str
    universe_en: str
    unsupported: frozenset[str] = frozenset()   # 没有数据源的指标：不显示、不计入维度分母
    has_moat: bool = False                      # 护城河依赖美股 10-K

    def universe(self, lang: str) -> str:
        return self.universe_zh if lang == "zh" else self.universe_en


_NO_EBIT_ESTIMATES = frozenset({"ebitda_fwd", "ebit_fwd", "ev_ebitda_fwd", "ev_ebit_fwd"})
_NO_REVENUE_ESTIMATES = frozenset({"ps_fwd", "ev_sales_fwd", "rev_fwd", "rev_fy1_90d"})
# 东财 / 经济通转换后的报表没有流动资产 / 流动负债与利息支出，对应两项稳健指标无数据源
_NO_LIQUIDITY_DETAIL = frozenset({"current_ratio", "interest_cov"})

PROFILES: dict[str, MarketProfile] = {
    "us": MarketProfile("us", "标普1500", "S&P 1500", has_moat=True),
    # A 股一致预期只有 EPS / 营收 / 净利润，没有 EBITDA / EBIT
    "cn": MarketProfile("cn", "A 股市值前 1800", "top 1,800 A-shares by market cap",
                         _NO_EBIT_ESTIMATES | _NO_LIQUIDITY_DETAIL),
    # 港股一致预期只有 EPS / 净利润
    "hk": MarketProfile("hk", "港股通及大中型港股", "Stock Connect and large/mid-cap HK stocks",
                        _NO_EBIT_ESTIMATES | _NO_REVENUE_ESTIMATES | _NO_LIQUIDITY_DETAIL),
}


def profile(market: str) -> MarketProfile:
    """市场配置；未知市场按美股（调用方先校验市场）。"""
    return PROFILES.get(market, PROFILES["us"])


def normalize_symbol(market: str, symbol: str) -> str:
    """各市场的存储代码：美股 BRK-B、A 股 6 位、港股 5 位（0700 / 0700.HK → 00700）。"""
    s = symbol.strip().upper()
    if market == "cn":
        return s.split(".")[0].removeprefix("SH").removeprefix("SZ").removeprefix("BJ").zfill(6)
    if market == "hk":
        return s.removesuffix(".HK").removeprefix("HK").zfill(5)
    return s.replace(".", "-")  # 与 universe.normalize_us_symbol 一致（BRK.B → BRK-B）
