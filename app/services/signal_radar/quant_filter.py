"""量化评级作为雷达准入门槛；只使用展示日已经生成的结果，不倒填历史。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.logging import logger
from app.models.quant_research import QuantResult
from app.schemas.signal_radar import RadarDayOut, RadarQuantFilterOut, RadarSignalOut
from app.services.quant_research import repository
from app.services.quant_research.grading import GRADE_ORDER
from app.services.quant_research.universe import normalize_us_symbol

MAX_AGE_DAYS = 7
KEEP_GRADES = {"A+", "A", "A-"}


@dataclass(frozen=True)
class QuantGrade:
    grade: str | None
    score: float | None
    as_of: date
    available_on: date


def grade_from_row(row: QuantResult) -> QuantGrade | None:
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
    return QuantGrade(grade if grade in GRADE_ORDER else None, score, row.as_of, max(dates))


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
    entries = [g for g in history.get(normalize_us_symbol(symbol), [])
               if g.as_of <= day and g.available_on <= day]
    if not entries:
        return None, "missing"
    entry = max(entries, key=lambda g: (g.as_of, g.available_on))
    if (day - entry.as_of).days > MAX_AGE_DAYS:
        return entry, "stale"
    if entry.grade is None or entry.score is None:
        return entry, "missing"
    return entry, "eligible" if entry.grade in KEEP_GRADES else "below_threshold"


def apply_filter(day: RadarDayOut, history: dict[str, list[QuantGrade]] | None,
                 symbols: list[str], *, preserve_sells: bool = False) -> RadarDayOut:
    """完整候选池先过滤，再交给技术排序；自选卖出提醒不受评级门槛限制。"""
    target = date.fromisoformat(day.date)
    grades = {s: grade_on(history or {}, s, target) for s in set(symbols)}
    stats = RadarQuantFilterOut(preserve_sells=preserve_sells, status="unavailable" if history is None else "ready")
    for _, status in grades.values():
        setattr(stats, status, getattr(stats, status) + 1)

    def select(signals: list[RadarSignalOut]) -> list[RadarSignalOut]:
        kept = []
        for signal in signals:
            entry, status = grades.get(signal.symbol, (None, "missing"))
            if status != "eligible" and not (preserve_sells and signal.side == "sell"):
                continue
            kept.append(signal.model_copy(update={
                "quant_grade": entry.grade if entry else None,
                "quant_score": entry.score if entry else None,
                "quant_as_of": entry.as_of.isoformat() if entry else None,
                "quant_status": status,
            }))
        return kept

    signals = select(day.signals)
    return day.model_copy(update={"signals": signals, "candidates": select(day.candidates),
                                 "buy_count": sum(s.side == "buy" for s in signals),
                                 "sell_count": sum(s.side == "sell" for s in signals), "quant_filter": stats})
