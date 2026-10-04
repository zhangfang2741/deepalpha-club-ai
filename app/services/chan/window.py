"""日线缠论的固定分析窗口。

缠论的笔 / 中枢划分对「从哪根 K 线开始算」敏感：多一根起点前的 K 线，开头多出一笔，czsc 分中枢是从
第一笔往后分组的，整条序列的中枢就整体错开，早期的买卖点会凭空出现或消失（MNST 2025-10-31 三买：
起点早 12 天就没了）。详情页用户可调起始日期、雷达用另一段窗口，同一只票同一天就会算出不同的早期结构。

所以日线的分析起点固定：截止日往前两年，再取该月 1 号（每月才变一次，不是每天都变，也让 K 线缓存键稳定）。
用户所选的起始日期只决定显示哪一段，不再影响结构；雷达、详情页、自选阶段、次级别的大级别用同一个起点。

显示起点之前再多算一年（预热，同样按月对齐）：缠论要先攒够若干笔、形成中枢才出买卖点（严格口径的一类
还要前面有两个已形成的中枢），从显示起点直接开算时显示区第一年几乎没有买卖点——8 只样本严格口径
2024-10~2025-09 只有 1 个，预热一年后 7 个，预热两年仍是 7 个（已收敛）。
周线 / 30 分钟保持原有的「可见起点 + 预热」口径。
"""
from __future__ import annotations

from datetime import date, timedelta

# 日线显示窗口：截止日往前两年
CANONICAL_DAILY_DAYS = 730
# 显示起点之前的预热年数（只参与计算、不显示）
DAILY_WARMUP_YEARS = 1


def canonical_daily_start(end_date: str | date) -> str:
    """日线固定分析起点（YYYY-MM-DD）：截止日 - 730 天，取当月 1 号。"""
    end = end_date if isinstance(end_date, date) else date.fromisoformat(str(end_date)[:10])
    return (end - timedelta(days=CANONICAL_DAILY_DAYS)).replace(day=1).isoformat()


def canonical_daily_fetch_start(end_date: str | date) -> str:
    """日线固定取数 / 计算起点（YYYY-MM-DD）：显示起点 canonical_daily_start 的同月往前一年（预热）。

    按年平移而不是再减 365 天：跨闰年时减天数会和显示起点差出一个月。
    """
    shown = date.fromisoformat(canonical_daily_start(end_date))
    return shown.replace(year=shown.year - DAILY_WARMUP_YEARS).isoformat()
