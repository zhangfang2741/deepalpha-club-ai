"""买卖点口径（宽松 / 严格 / …）：统一接口 + 多套实现。

同一份笔 / 中枢结构上，「什么算买卖点」有不同口径。每种口径实现 SignalPolicy 接口，
在 SIGNAL_POLICIES 注册；analyzer、详情接口、次级别、信号雷达都只按名字取口径、走接口，
不写 if mode == ... 的分支。新增一种口径（比如「中等」）：写一个实现类、注册即可——
雷达缓存键按 policy.version 自动隔离，定时预热遍历注册表自动覆盖，App 从
GET /chan/signal-modes 读取可选项。

改了某口径的判定逻辑，务必升它的 version（雷达缓存键带版本，否则旧快照要等 TTL 过期）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.services.chan.czsc_signals import BsEvent, SignalFamily
from app.services.chan.divergence import DivergenceResult
from app.services.chan.pivot import Pivot
from app.services.chan.signals import Signal, generate_all_signals, generate_loose_signals
from app.services.chan.stroke import Stroke


class SignalPolicy(Protocol):
    """买卖点口径接口。"""

    # 只读元信息（实现类为 frozen dataclass）
    @property
    def name(self) -> str:
        """口径名（接口 / 缓存 / App 设置里用的键），如 loose / strict。"""
        ...

    @property
    def version(self) -> str:
        """判定逻辑版本，进雷达缓存键；改了逻辑必须升。"""
        ...

    @property
    def label_zh(self) -> str: ...
    @property
    def label_en(self) -> str: ...
    @property
    def description_zh(self) -> str: ...
    @property
    def description_en(self) -> str: ...

    @property
    def czsc_families(self) -> tuple[SignalFamily, ...]:
        """扫描时启用的 czsc 信号族。"""
        ...

    def assemble(
        self, events: list[BsEvent], strokes: list[Stroke], divergences: list[DivergenceResult],
        pivots: list[Pivot], lang: str, *, stroke_done_at: dict[str, str],
    ) -> list[Signal]:
        """把 czsc 事件 + 结构组装成买卖点（按时间排序）。"""
        ...

    def split_unconfirmed(self, signals: list[Signal]) -> tuple[list[Signal], list[Signal]]:
        """在 confirmed 标注之后调用：返回（买卖点, 「待确认」候选）。"""
        ...


@dataclass(frozen=True)
class _PolicyInfo:
    name: str
    version: str
    label_zh: str
    label_en: str
    description_zh: str
    description_en: str
    czsc_families: tuple[SignalFamily, ...]


class LoosePolicy(_PolicyInfo):
    """宽松（默认）：czsc 原生一 / 二 / 三类，最后一笔上的也算（标未确认）。"""

    def assemble(self, events, strokes, divergences, pivots, lang, *, stroke_done_at):  # noqa: ARG002
        return generate_loose_signals(events, strokes, divergences, pivots, lang)

    def split_unconfirmed(self, signals):
        return signals, []


class StrictPolicy(_PolicyInfo):
    """严格：按缠论原文定义（趋势背驰一类、一类后的二类、中枢推出的三类），只落在已完成的笔上。"""

    def assemble(self, events, strokes, divergences, pivots, lang, *, stroke_done_at):
        return generate_all_signals(events, strokes, divergences, pivots, lang, stroke_done_at=stroke_done_at)

    def split_unconfirmed(self, signals):
        # 最后一笔还在走（端点可能延伸甚至回到中枢），其上的买卖点尚不成立：移入候选
        return [s for s in signals if s.confirmed], [s for s in signals if not s.confirmed]


# 版本记录——strict：std1 严格按原文；std2 中枢「已形成」判定 + 一类被跌破作废 + 只落已完成的笔；
# std3 新增 candidates；std4 日期改为成立日（所在笔的下一笔走完）。loose：loose1 严格化之前的口径。
_ALL: tuple[SignalPolicy, ...] = (
        LoosePolicy(
            name="loose", version="loose1", label_zh="宽松", label_en="Relaxed",
            description_zh="信号更多、出得更早：盘整里的背驰也算一类，二、三类按价格密集区与均线辅助判断，"
                           "最后一笔还在走时也先标出（未确认）。",
            description_en="More and earlier signals: divergence inside a range also counts as type-1; "
                           "type-2/3 use price clusters and a moving-average filter; signals on the unfinished "
                           "last leg are shown as unconfirmed.",
            czsc_families=("first", "second", "third"),
        ),
        StrictPolicy(
            name="strict", version="std4", label_zh="严格", label_en="Strict",
            description_zh="严格按缠论原文：一类须趋势背驰，二类须跟在一类之后，三类须离开中枢后回落 / 反弹"
                           "没有回到中枢；只认已走完的笔，最后一笔上的单列为「待确认」。",
            description_en="Textbook Chan: type-1 needs a trend divergence, type-2 must follow a type-1, "
                           "type-3 must not return to the pivot; only completed legs count, signals on the "
                           "last leg are listed as pending.",
            czsc_families=("first",),
        ),
)
SIGNAL_POLICIES: dict[str, SignalPolicy] = {p.name: p for p in _ALL}

DEFAULT_MODE = "loose"


def get_policy(mode: str | None) -> SignalPolicy:
    """按名字取口径；未知 / 空回退默认口径。"""
    return SIGNAL_POLICIES.get(mode or DEFAULT_MODE) or SIGNAL_POLICIES[DEFAULT_MODE]


def normalize_mode(mode: str | None) -> str:
    """口径名归一化（未知回退默认），供缓存键与响应使用。"""
    return get_policy(mode).name
