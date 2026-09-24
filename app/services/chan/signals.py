"""缠论三类买卖点：czsc 结构信号事件 → 带强度/背驰/文案的 Signal。

「是否构成买卖点」由 czsc_signals.scan_bs_events 判定；这里只负责把事件落到
所属笔端点，并用本地背驰度量（一类）与中枢级别+余量（二/三类）给出强度。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.chan.bias import SEGMENT_WEIGHT, STROKE_WEIGHT
from app.services.chan.czsc_signals import BsEvent
from app.services.chan.divergence import DivergenceResult
from app.services.chan.i18n import is_en
from app.services.chan.pivot import Pivot
from app.services.chan.stroke import Stroke

# 二/三类买卖点强度：中枢级别（线段级中枢权重高于笔级，复用 bias.py 里已定义
# 的同一套权重，不能另起一套数字）+ 回踩/反抽落点离中枢边界的余地（相对中枢
# 高度归一化，越远离边界说明多空争夺的胜负越坚决）。
# 之前二类固定"medium"、三类固定"strong"，是完全不反映具体情况的占位符——
# 同是三类信号，贴着边界勉强不回中枢的和远远甩开中枢的，强度应该不一样。
_MARGIN_WEIGHT = 1.5
_TYPE23_STRONG_THRESHOLD = 2.5
_TYPE23_MEDIUM_THRESHOLD = 1.5


def _type23_strength(pivot: Pivot, margin_ratio: float) -> Literal["strong", "medium", "weak"]:
    """二/三类买卖点强度：中枢级别 + 回踩/反抽余地加权后分三档。

    margin_ratio：回踩/反抽落点离中枢边界的距离，相对中枢高度归一化（0=贴着
    边界，1=已拉开一整个中枢高度），由调用方按买/卖、二/三类各自的边界算好传入。
    """
    level_weight = SEGMENT_WEIGHT if pivot.level == "segment" else STROKE_WEIGHT
    score = level_weight + min(max(margin_ratio, 0.0), 1.0) * _MARGIN_WEIGHT
    if score >= _TYPE23_STRONG_THRESHOLD:
        return "strong"
    if score >= _TYPE23_MEDIUM_THRESHOLD:
        return "medium"
    return "weak"


def _margin_ratio(pivot: Pivot, boundary: float, retrace_price: float) -> float:
    """回踩/反抽落点离 boundary 有多远，相对中枢高度归一化；中枢高度异常时退回 0。"""
    height = pivot.height
    if height <= 0:
        return 0.0
    return abs(retrace_price - boundary) / height


@dataclass
class Signal:
    """买卖点信号"""
    type: Literal["buy1", "buy2", "buy3", "sell1", "sell2", "sell3"]
    time: str
    price: float
    strength: Literal["strong", "medium", "weak"]
    divergence: DivergenceResult | None
    description: str
    # 信号是否已确认：落在未确认（最后一笔）之上的信号需后续K线验证
    confirmed: bool = True
    # 输出语言（由 generate_all_signals 统一注入），驱动 label 的中英
    lang: str = "zh"

    @property
    def label(self) -> str:
        if is_en(self.lang):
            labels_en = {
                "buy1": "1st Buy", "buy2": "2nd Buy", "buy3": "3rd Buy",
                "sell1": "1st Sell", "sell2": "2nd Sell", "sell3": "3rd Sell",
            }
            return labels_en.get(self.type, self.type)
        labels = {
            "buy1": "一买", "buy2": "二买", "buy3": "三买",
            "sell1": "一卖", "sell2": "二卖", "sell3": "三卖",
        }
        return labels.get(self.type, self.type)

    @property
    def is_buy(self) -> bool:
        return self.type.startswith("buy")


def _post_pivot_strokes(strokes: list[Stroke], pivots: list[Pivot], idx: int) -> list[Stroke]:
    """某中枢「离开段」所在的笔窗口：从突破笔开始、到下一个中枢形成之前（中枢阶段判定用）。

    二 / 三类买卖点只属于离开该中枢的那一段。旧实现对每个历史中枢都扫描其后
    无限远的笔，导致一个几个月前的旧中枢在价格偶然回到其价格带时误触发信号
    （例如 FIG 8 月的价格回到 12 月旧中枢带被误判成二卖）。此处以「下一个中枢的
    起点」为上界，把每个中枢的信号搜索限制在它自己的离开段内。

    中枢延伸判定（见 pivot.py）只要笔与 [ZD, ZG] 有重叠就并入 pivot.elements——
    真正的突破笔因为起点必然还在区间内，永远会被判定为「重叠」而吞并进中枢，
    连带回踩笔如果落回区间内也会一并吞并。结果是突破笔/回踩笔从未出现在
    `end_time` 之后，二/三类买卖点因此在真实数据上几乎永远无法触发。这里把
    中枢自身吞并进去的延伸段（第 4 段起）接回来，才能还原出完整的「突破笔 +
    回踩笔」序列供阶段判定的突破/回踩配对使用。
    """
    pivot = pivots[idx]
    upper = pivots[idx + 1].start_time if idx + 1 < len(pivots) else None
    absorbed = pivot.elements[3:] if pivot.level == "stroke" else []
    post = [
        s for s in strokes
        if s.start_time >= pivot.end_time and (upper is None or s.start_time < upper)
    ]
    return [*absorbed, *post]


# 二/三类买卖点强度的参照边界：回踩/反抽落点离哪条中枢边界越远越坚决
_TYPE23_BOUNDARY = {"buy2": "zd", "sell2": "zg", "buy3": "zg", "sell3": "zd"}


def _latest_pivot_before(pivots: list[Pivot], time: str) -> Pivot | None:
    """信号时刻之前已结束的最近中枢（结束时间最晚者）；尚未结束的中枢不参与，避免回看未来。"""
    done = [p for p in pivots if p.end_time <= time]
    return max(done, key=lambda p: p.end_time) if done else None


def _span_count(span: str) -> str:
    return span[:-1] if span.endswith("笔") else ""


def _describe(sig_type: str, time: str, price: float, span: str,
              div: DivergenceResult | None, lang: str) -> str:
    n = _span_count(span)
    area = f"，MACD面积比值={div.area_ratio:.2f}" if div else ""
    area_en = f"; MACD area ratio={div.area_ratio:.2f}" if div else ""
    if is_en(lang):
        legs = f"the last of {n} legs" if n else "the last leg"
        texts = {
            "buy1": f"Type-1 buy: at {time}, {legs} of the decline made a new low ({price:.2f}) with weaker "
                    f"force than earlier legs (price range plus volume/duration fading) — a bottom divergence{area_en}",
            "sell1": f"Type-1 sell: at {time}, {legs} of the advance made a new high ({price:.2f}) with weaker "
                     f"force than earlier legs (price range plus volume/duration fading) — a top divergence{area_en}",
            "buy2": f"Type-2 buy: at {time}, the pullback low ({price:.2f}) landed in a zone where several earlier "
                    f"turning points clustered, finding support without a new low",
            "sell2": f"Type-2 sell: at {time}, the rebound high ({price:.2f}) met a zone where several earlier "
                     f"turning points clustered, capped without a new high",
            "buy3": f"Type-3 buy: at {time}, after the prior five legs formed a pivot, the pullback low "
                    f"({price:.2f}) stayed above the pivot top with the moving average stepping higher",
            "sell3": f"Type-3 sell: at {time}, after the prior five legs formed a pivot, the rebound high "
                     f"({price:.2f}) stayed below the pivot bottom with the moving average stepping lower",
        }
    else:
        legs = f"近{n}笔" if n else "近几笔"
        texts = {
            "buy1": f"一类买点：{time} {legs}下跌中末笔创新低（{price:.2f}），但下跌力度弱于前段"
                    f"（价差与量能/时长同步衰减），构成底背驰{area}",
            "sell1": f"一类卖点：{time} {legs}上涨中末笔创新高（{price:.2f}），但上涨力度弱于前段"
                     f"（价差与量能/时长同步衰减），构成顶背驰{area}",
            "buy2": f"二类买点：{time} 回调低点（{price:.2f}）落在此前多次转折形成的价格密集区，获得支撑、未再创新低",
            "sell2": f"二类卖点：{time} 反弹高点（{price:.2f}）触及此前多次转折形成的价格密集区，受压回落、未再创新高",
            "buy3": f"三类买点：{time} 前五笔构成中枢后，回调低点（{price:.2f}）仍在中枢上沿之上未回中枢，且均线逐级抬升",
            "sell3": f"三类卖点：{time} 前五笔构成中枢后，反弹高点（{price:.2f}）仍在中枢下沿之下未回中枢，且均线逐级下移",
        }
    return texts[sig_type]


def generate_all_signals(
    events: list[BsEvent],
    strokes: list[Stroke],
    divergences: list[DivergenceResult],
    pivots: list[Pivot],
    lang: str = "zh",
) -> list[Signal]:
    """把 czsc 买卖点事件组装成 Signal，按时间排序、(类型, 时间) 去重。

    - 落点：所属笔的终点（与图上笔端点对齐，_mark_confirmations 据此判断是否确认）。
    - 一类强度：只反映该笔的背驰幅度（本地 MACD 面积 + DIF 双过滤）；本地度量未确认
      背驰时降为 weak、不挂背驰对象——czsc 的一买判据是笔力度，二者可能不一致。
    - 二/三类强度：信号前最近已结束中枢的级别 + 落点离对应边界的余量（_type23_strength）；
      无可依中枢时为 weak。
    """
    div_by_end = {s.end_time: dv for s, dv in zip(strokes, divergences, strict=False)}
    signals: list[Signal] = []
    seen: set[tuple[str, str]] = set()
    for ev in sorted(events, key=lambda e: e.bi_end_time):
        key = (ev.type, ev.bi_end_time)
        if key in seen:
            continue
        seen.add(key)

        div: DivergenceResult | None = None
        strength: Literal["strong", "medium", "weak"] = "weak"
        if ev.type in ("buy1", "sell1"):
            dv = div_by_end.get(ev.bi_end_time)
            if dv is not None and dv.is_diverged and dv.strength != "none":
                div = dv
                strength = dv.strength  # type: ignore[assignment]
        else:
            pivot = _latest_pivot_before(pivots, ev.bi_end_time)
            if pivot is not None:
                boundary = getattr(pivot, _TYPE23_BOUNDARY[ev.type])
                strength = _type23_strength(pivot, _margin_ratio(pivot, boundary, ev.bi_end_price))

        signals.append(Signal(
            type=ev.type,
            time=ev.bi_end_time,
            price=ev.bi_end_price,
            strength=strength,
            divergence=div,
            description=_describe(ev.type, ev.bi_end_time, ev.bi_end_price, ev.span, div, lang),
            lang=lang,
        ))
    return signals
