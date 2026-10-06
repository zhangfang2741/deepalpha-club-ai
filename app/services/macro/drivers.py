"""宏观驱动因素：定义 + 纯函数判定（方向、对股票的影响、大白话）。

只描述环境，不出现买卖导向的词，也不出现数据供应商名。美元 / 原油没有可用的指数序列，
用跟踪它们的基金价格近似，只展示涨跌幅（unit=change），不展示点位。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas.macro import MacroDriverOut

WINDOW = 20  # 近 20 个交易日


@dataclass(frozen=True)
class DriverSpec:
    """一个驱动因素的定义（单位、持平阈值、上行影响、三种文案）。"""
    key: str
    name_zh: str
    name_en: str
    unit: str  # percent / point / change
    flat_band: float  # |变化| 小于它算持平（percent=基点，point=点，change=%）
    # 上行对股票的影响：negative（利率、美元、波动、油价上行偏压制）/ neutral
    up_impact: str
    text_up: tuple[str, str]
    text_down: tuple[str, str]
    text_flat: tuple[str, str]


US_DRIVERS: list[DriverSpec] = [
    DriverSpec(
        key="us10y", name_zh="10 年期美债利率", name_en="10Y Treasury Yield", unit="percent", flat_band=10,
        up_impact="negative",
        text_up=("利率上行，股票估值承压，成长股更敏感", "Yields rising: pressure on valuations, growth stocks most sensitive"),
        text_down=("利率回落，股票估值压力减轻", "Yields falling: less pressure on valuations"),
        text_flat=("利率基本持平", "Yields roughly unchanged"),
    ),
    DriverSpec(
        key="curve", name_zh="10Y-2Y 利差", name_en="10Y-2Y Spread", unit="percent", flat_band=8,
        up_impact="neutral",
        text_up=("长短端利差走阔", "Yield curve steepening"),
        text_down=("长短端利差收窄", "Yield curve flattening"),
        text_flat=("长短端利差基本持平", "Yield curve roughly unchanged"),
    ),
    DriverSpec(
        key="dollar", name_zh="美元", name_en="US Dollar", unit="change", flat_band=1.0,
        up_impact="negative",
        text_up=("美元走强，全球资金偏谨慎", "Dollar strengthening: global risk appetite tends to cool"),
        text_down=("美元走弱，全球资金偏宽松", "Dollar weakening: looser global financial conditions"),
        text_flat=("美元基本持平", "Dollar roughly unchanged"),
    ),
    DriverSpec(
        key="vix", name_zh="VIX 波动率", name_en="VIX", unit="point", flat_band=1.5,
        up_impact="negative",
        text_up=("波动率上升，市场避险情绪升温", "Volatility rising: risk aversion picking up"),
        text_down=("波动率回落，市场情绪趋于平稳", "Volatility easing: markets calming down"),
        text_flat=("波动率基本持平", "Volatility roughly unchanged"),
    ),
    DriverSpec(
        key="oil", name_zh="原油", name_en="Crude Oil", unit="change", flat_band=3.0,
        up_impact="negative",
        text_up=("油价上涨，通胀压力上升", "Oil rising: inflation pressure building"),
        text_down=("油价下跌，通胀压力缓解", "Oil falling: inflation pressure easing"),
        text_flat=("油价基本持平", "Oil roughly unchanged"),
    ),
]

DRIVERS_BY_MARKET: dict[str, list[DriverSpec]] = {"us": US_DRIVERS}

_UNAVAILABLE = ("暂无数据", "No data")
_INVERTED = ("利差倒挂，市场在定价经济放缓", "Curve inverted: markets pricing in a slowdown")


def _pick(pair: tuple[str, str], lang: str) -> str:
    return pair[1] if lang == "en" else pair[0]


def evaluate_driver(spec: DriverSpec, series: list[tuple[str, float]], lang: str = "zh") -> MacroDriverOut:
    """series 为按日期升序的 (日期, 值)。不足 WINDOW+1 个点时只给当前值、不判方向。"""
    name = spec.name_en if lang == "en" else spec.name_zh
    if not series:
        return MacroDriverOut(key=spec.key, name=name, unit=spec.unit, impact="neutral",
                              text=_pick(_UNAVAILABLE, lang))
    as_of, latest = series[-1]
    value = None if spec.unit == "change" else round(latest, 2)
    if len(series) <= WINDOW:
        return MacroDriverOut(key=spec.key, name=name, value=value, unit=spec.unit, impact="neutral",
                              text=_pick(_UNAVAILABLE, lang), as_of=as_of, flat_band=spec.flat_band)
    base = series[-1 - WINDOW][1]
    if spec.unit == "percent":
        change = (latest - base) * 100  # 百分点 → 基点
    elif spec.unit == "point":
        change = latest - base
    else:
        change = (latest / base - 1) * 100 if base else 0.0
    if abs(change) < spec.flat_band:
        direction, impact, text = "flat", "neutral", spec.text_flat
    elif change > 0:
        direction, impact, text = "up", spec.up_impact, spec.text_up
    else:
        direction, text = "down", spec.text_down
        impact = "positive" if spec.up_impact == "negative" else "neutral"
    if spec.key == "curve" and latest < 0:
        text = _INVERTED
    return MacroDriverOut(key=spec.key, name=name, value=value, unit=spec.unit, change=round(change, 1),
                          direction=direction, impact=impact, text=_pick(text, lang), as_of=as_of,
                          flat_band=spec.flat_band)
