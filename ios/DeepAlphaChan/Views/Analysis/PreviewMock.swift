#if DEBUG
import Foundation
import SwiftUI

/// 仅用于 SwiftUI 预览和布局自查的假数据。
///
/// 包在 #if DEBUG 里，不会进 Release 包。存在的理由：分析结果态是这个 App 最
/// 复杂的界面，没有真实后端数据时无法目视检查布局，而布局问题编译器发现不了。
enum PreviewMock {
    static var analysis: ChanAnalysis {
        ChanAnalysis(
            symbol: "AAPL",
            barsCount: 62,
            mergedCandles: candles,
            fractals: [],
            strokes: [],
            segments: [],
            strokePivots: [],
            segmentPivots: [],
            macd: nil,
            signals: signals,
            currentTrend: "up",
            walkType: "up_trend",
            walkTypeLabel: "当前为上涨趋势（中枢依次抬高）",
            trendOutlook: "continuation_up",
            trendOutlookLabel: "上涨走势延续",
            summary: "近期走出一段向上线段，价格站上前一中枢上沿并完成回踩确认，结构偏强。当前处于线段延伸阶段，尚未出现同级别背驰。",
            recommendation: Recommendation(
                action: "hold",
                actionLabel: "持有观望",
                bias: "bullish",
                reasons: [
                    "价格突破中枢上沿后回踩不破，构成三买结构",
                    "向上线段尚未出现背驰迹象，力度仍在延续",
                ],
                caveats: [
                    "距离中枢上沿已有一定涨幅，追高性价比下降",
                    "若跌回中枢内部，三买结构失效",
                ]
            ),
            narrative: MarketNarrative(
                phase: "breakout",
                phaseLabel: "突破上行",
                headline: "股价站上了前期的整理区间，多方掌握主动，目前处在上涨通道里。",
                details: [
                    "短期节奏（笔）向上，处于上升的一段中。",
                    "当前价站在前期反复争夺的价格区间（中枢）上方，多方暂时占上风。",
                    "近期放量上涨，成交明显放大、资金愿意追，上涨相对健康。",
                ]
            ),
            pendingNotes: [
                "最新一笔尚未确认，需等待后续 K 线验证顶分型是否成立",
                "周线级别中枢尚未形成，当前判断仅适用于日线级别",
            ],
            pivotPhase: PivotPhase(
                phase: "leaving",
                phaseLabel: "向上离开中枢",
                direction: "up",
                pivot: Pivot(zg: 388.0, zd: 372.0, gg: 390.5, dd: 370.2,
                             startTime: "2026-05-12", endTime: "2026-06-20",
                             level: .stroke, confirmed: true),
                checklist: [
                    PhaseChecklistItem(label: "形成中枢", detail: "372.00–388.00", state: .done),
                    PhaseChecklistItem(label: "向上离开中枢", detail: "现价 392.16 已站上 ZG 388.00", state: .done),
                    PhaseChecklistItem(label: "等待离开段走完后回抽确认", detail: "", state: .pending),
                ],
                reason: "现价 392.16 已站上 ZG 388.00，最新向上笔离开了中枢区间。",
                confirmed: true,
                branches: [
                    PhaseBranch(outcome: "type3", conditionLabel: "回踩守住 ZG 388.00 以上，不回中枢",
                                resultLabel: "确认三买（趋势确认，最强）"),
                    PhaseBranch(outcome: "type2", conditionLabel: "回踩落在中枢区间内，未破 ZD 372.00",
                                resultLabel: "确认二买（中枢升级，弱于三买）"),
                    PhaseBranch(outcome: "back_to_range", conditionLabel: "回踩跌破 ZD 372.00，重新进入中枢",
                                resultLabel: "假突破，回到中枢震荡"),
                ],
                stageGuide: StageGuide(
                    currentIndex: 2,
                    steps: [
                        StageGuideStep(key: "pivot_forming", title: "中枢形成", detail: "三段重叠围出 372.00–388.00"),
                        StageGuideStep(key: "pivot_oscillating", title: "中枢震荡", detail: "区间内反复，中枢延伸"),
                        StageGuideStep(key: "leaving", title: "离开段", detail: "向上离开中枢，候选第三类买点"),
                        StageGuideStep(key: "retrace_confirmed", title: "回抽确认", detail: "回抽不进中枢 → 确认三买"),
                        StageGuideStep(key: "divergence_turn", title: "背驰/转折", detail: "趋势末端背驰 → 一类买卖点"),
                    ],
                    whyItMatters: "离开段是缠论趋势能否延续的分水岭：向上离开中枢后若回抽不进中枢，就确认三买、中枢升级、趋势打开；若回抽跌回中枢，则回到震荡。"
                )
            ),
            structureLayers: [
                StructureLayer(layer: "stroke", label: "笔", title: "向上笔形成中",
                                detail: "最新底分型后向上延伸，顶分型尚未确认"),
                StructureLayer(layer: "segment", label: "线段", title: "向下线段未结束",
                                detail: "当前笔尚未破坏线段结构，线段延续"),
                StructureLayer(layer: "pivot", label: "中枢", title: "向上离开中枢",
                                detail: "现价 392.16 已站上 ZG 388.00，最新向上笔离开了中枢区间。"),
                StructureLayer(layer: "signal", label: "买卖点", title: "三买候选",
                                detail: "落在未确认笔上，属左侧预判。"),
            ],
            structureHeadline: "当前处于向下线段中的一根向上笔，现价站上中枢上方，最近出现三买（候选）。"
        )
    }

    private static var candles: [MergedCandle] {
        (0..<62).map { i in
            let base = 180.0 + Double(i) * 0.6 + sin(Double(i) / 4) * 5
            return MergedCandle(
                idx: i,
                time: String(format: "2026-06-%02d", (i % 28) + 1),
                high: base + 2.4,
                low: base - 2.1,
                open: base - 0.8,
                close: base + 1.1,
                volume: 2_000_000 + abs(sin(Double(i) / 3)) * 3_000_000
            )
        }
    }

    private static var signals: [Signal] {
        [
            Signal(type: .buy3, label: "三买", time: "2026-07-18", price: 208.34,
                   strength: .strong, isBuy: true,
                   description: "突破前中枢上沿后回踩不破，确认第三类买点。",
                   areaRatio: nil, confirmed: true,
                   priceRatio: nil, volumeRatio: nil, lengthRatio: nil),
            Signal(type: .buy2, label: "二买", time: "2026-06-25", price: 191.02,
                   strength: .medium, isBuy: true,
                   description: "一买后反弹回调不创新低，构成第二类买点。",
                   areaRatio: nil, confirmed: true,
                   priceRatio: nil, volumeRatio: nil, lengthRatio: nil),
            Signal(type: .sell1, label: "一卖", time: "2026-08-14", price: 219.60,
                   strength: .strong, isBuy: false,
                   description: "创新高但力度弱于前段，出现盘整背驰：价差为前段的 0.58 倍、量能 0.71 倍、时长 0.90 倍。",
                   areaRatio: nil, confirmed: false,
                   priceRatio: 0.58, volumeRatio: 0.71, lengthRatio: 0.90),
        ]
    }
}

// Xcode 画布预览。分析结果态是这个 App 最复杂的界面，没有这些预览就只能
// 靠「起后端 → 登录 → 输代码 → 等分析」才能看一眼布局。

#Preview("形态分析") {
    ScrollView { AnalysisSection(analysis: PreviewMock.analysis).padding(Theme.contentHInset) }
        .background(Theme.background)
        .preferredColorScheme(.dark)
}

#Preview("买卖点") {
    ScrollView { SignalListSection(analysis: PreviewMock.analysis).padding(14) }
        .background(Theme.background)
        .preferredColorScheme(.dark)
}

#Preview("词条详情") {
    NavigationStack {
        LessonDetailView(article: LessonStore.all.first(where: { $0.id == "pivot" })
            ?? LessonArticle(id: "x", title: "缺少内容", summary: "", body: ""))
    }
    .preferredColorScheme(.dark)
}

#Preview("学习列表") {
    LearnTabView().preferredColorScheme(.dark)
}

#Preview("阶段讲解") {
    NavigationStack {
        PivotPhaseGuideSheet(pivotPhase: PreviewMock.analysis.pivotPhase!)
    }
    .preferredColorScheme(.dark)
}
#endif
