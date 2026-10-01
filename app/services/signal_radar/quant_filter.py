"""量化评级附加到雷达气泡（只标注，不参与排序、不排除任何信号）；只使用展示日已经生成的结果，不倒填历史。

2026-10-01 起雷达只呈现事实：此前的「基本面排雷」（盈利能力 F / EPS 修正 F 的买点、EPS 修正 A+ 的卖点
不上榜）已取消，评级照常标在气泡上，由用户自己看。改这里的行为须升 service._mode_ns 的 quant 版本。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.logging import logger
from app.schemas.signal_radar import RadarDayOut, RadarQuantFilterOut, RadarSignalOut
from app.services.quant_research import repository
from app.services.quant_research.grading import GRADE_ORDER
from app.services.quant_research.universe import normalize_us_symbol

MAX_AGE_DAYS = 7
# 2026-09-30 产品决定：雷达暂不引入评级作为排序权重，只把评级 mark 到气泡上
# （QUANT_WEIGHT=0 时排序回到纯技术分）。恢复加权时改回 0.5，并升雷达缓存键
# _mode_ns 的 quant 版本，否则旧缓存里的顺序还是旧权重排的。
QUANT_WEIGHT = 0.0


@dataclass(frozen=True)
class QuantGrade:
    grade: str | None
    score: float | None
    as_of: date
    available_on: date
    profitability: str | None = None
    revisions: str | None = None


def grade_from_row(row: repository.QuantGradeSnapshot) -> QuantGrade | None:
    """更新时刻也参与可用日判断，避免事后覆盖的历史结果泄漏到过去。"""
    payload = row.payload_zh or row.payload_en or {}
    overall = payload.get("overall") or {}
    grade = overall.get("grade")
    value = overall.get("score")
    score = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    if score is not None and (not math.isfinite(score) or not 0 <= score <= 100):
        score = None
    dates = [row.as_of, row.created_at.date(), row.updated_at.date()]
    for key in ("price_date", "filing_date", "estimates_date"):
        raw = (payload.get("as_of") or {}).get(key)
        if raw:
            try:
                dates.append(date.fromisoformat(str(raw)[:10]))
            except ValueError:
                return None
    dims = {k: v if v in GRADE_ORDER else None
            for k, v in ((k, (row.grades or {}).get(f"d:{k}")) for k in ("profitability", "revisions"))}
    return QuantGrade(grade if grade in GRADE_ORDER else None, score, row.as_of, max(dates), **dims)


async def load_grades(market: str, symbols: list[str], days: list[str]) -> dict[str, list[QuantGrade]] | None:
    """一次批量读取全股票池。None 表示查询失败，空字典表示确实没有评级。"""
    if market != "us" or not symbols or not days:
        return {}
    try:
        rows = await repository.get_quant_grade_history(
            market, sorted({normalize_us_symbol(s) for s in symbols}),
            date.fromisoformat(min(days)) - timedelta(days=MAX_AGE_DAYS), date.fromisoformat(max(days)),
        )
        history: dict[str, list[QuantGrade]] = {}
        for row in rows:
            entry = grade_from_row(row)
            if entry is not None:
                history.setdefault(normalize_us_symbol(row.symbol), []).append(entry)
        return history
    except Exception:
        logger.exception("signal_radar_quant_read_failed", market=market)
        return None


def grade_on(history: dict[str, list[QuantGrade]], symbol: str, day: date) -> tuple[QuantGrade | None, str]:
    """取当时最新一条，缺失或过期时不回退到更老的优良评级。"""
    entries = [g for g in history.get(normalize_us_symbol(symbol), [])
               if g.as_of <= day and g.available_on <= day]
    if not entries:
        return None, "missing"
    entry = max(entries, key=lambda g: (g.as_of, g.available_on))
    if (day - entry.as_of).days > MAX_AGE_DAYS:
        return entry, "stale"
    if entry.grade is None or entry.score is None:
        return entry, "missing"
    return entry, "eligible"


def attach_grades(day: RadarDayOut, history: dict[str, list[QuantGrade]] | None,
                 symbols: list[str]) -> RadarDayOut:
    """给当天的信号附加评级（只标注）。评级缺失或查询故障均原样保留信号。"""
    target = date.fromisoformat(day.date)
    grades = {s: grade_on(history or {}, s, target) for s in set(symbols)}
    stats = RadarQuantFilterOut(status="unavailable" if history is None else "ready", mode="marked")
    for _, status in grades.values():
        setattr(stats, status, getattr(stats, status) + 1)

    def mark(signals: list[RadarSignalOut]) -> list[RadarSignalOut]:
        out = []
        for signal in signals:
            entry, status = grades.get(signal.symbol, (None, "missing"))
            out.append(signal.model_copy(update={
                "quant_grade": entry.grade if entry else None,
                "quant_score": entry.score if entry else None,
                "quant_as_of": entry.as_of.isoformat() if entry else None,
                "quant_status": status,
            }))
        return out

    return day.model_copy(update={"signals": mark(day.signals), "candidates": mark(day.candidates),
                                 "quant_filter": stats})


def rating_factor(signal: RadarSignalOut) -> float:
    """13 档等级等距映射到 0~1；缺失或过期取中性 0.5，不视为低评级。"""
    if signal.quant_status != "eligible" or signal.quant_grade not in GRADE_ORDER:
        return 0.5
    return 1.0 - GRADE_ORDER.index(signal.quant_grade) / (len(GRADE_ORDER) - 1)
