"""按历史某个时间点重建缠论分析快照。

回答"这条历史信号发生当天，中枢处于哪个生命周期阶段"这类回溯性问题
（信号雷达气泡深浅用，见 app/services/signal_radar/service.py）。

不是另起一套历史状态机——直接把 `ChanAnalysisResult` 截断到 `as_of_time`
之前的部分，原样喂给 `build_pivot_phase`，判定口径和"分析当下"完全一致，
不会出现两套算法各说各话。同一只股票在看板上展示的历史信号，因此各自能
准确反映自己发生那天的真实阶段，而不是全部套用"今天"的阶段快照。
"""
from __future__ import annotations

from app.services.chan.analyzer import ChanAnalysisResult
from app.services.chan.pivot import Pivot
from app.services.chan.pivot_phase import PivotPhase, build_pivot_phase


def _truncate_pivot(pivot: Pivot, as_of_time: str) -> Pivot | None:
    """把中枢截断到 as_of_time 之前完成的部分。

    ZG/ZD 由最初三段固定（缠论标准），只要那三段都在 as_of_time 之前完成，
    截断不影响 ZG/ZD——`build_pivot_phase` 的判定只依赖 zg/zd 和
    `elements`，不依赖 GG/DD，这里保留原值即可。如果连最初三段都还没在
    as_of_time 之前凑齐，说明这个中枢在当时还不存在，返回 None。
    """
    kept = [e for e in pivot.elements if e.end_time <= as_of_time]
    if len(kept) < 3:
        return None
    return Pivot(zg=pivot.zg, zd=pivot.zd, gg=pivot.gg, dd=pivot.dd,
                 start_time=pivot.start_time, end_time=kept[-1].end_time,
                 level=pivot.level, elements=kept, confirmed=True)


def truncate_as_of(result: ChanAnalysisResult, as_of_time: str) -> ChanAnalysisResult:
    """构造一份「看起来像分析在 as_of_time 那天刚跑完」的截断快照。"""
    truncated = ChanAnalysisResult(symbol=result.symbol, bars_count=result.bars_count)
    truncated.strokes = [s for s in result.strokes if s.end_time <= as_of_time]
    # divergences 与 strokes 按下标一一对应（见 pivot_phase._find_divergence_turn），
    # 截断笔序列后取相同前缀长度即可保持对齐。
    truncated.divergences = result.divergences[:len(truncated.strokes)]
    truncated.stroke_pivots = [
        p for p in (_truncate_pivot(p, as_of_time) for p in result.stroke_pivots) if p is not None
    ]
    truncated.segment_pivots = [
        p for p in (_truncate_pivot(p, as_of_time) for p in result.segment_pivots) if p is not None
    ]
    truncated.merged_candles = [c for c in result.merged_candles if c.time <= as_of_time]
    return truncated


def pivot_phase_as_of(result: ChanAnalysisResult, as_of_time: str, lang: str = "zh") -> PivotPhase | None:
    """回溯 as_of_time 那天的中枢生命周期阶段，判定口径与 build_pivot_phase 完全一致。"""
    return build_pivot_phase(truncate_as_of(result, as_of_time), lang)
