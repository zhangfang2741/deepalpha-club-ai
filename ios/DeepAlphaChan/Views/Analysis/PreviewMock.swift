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
            pendingNotes: [
                "最新一笔尚未确认，需等待后续 K 线验证顶分型是否成立",
                "周线级别中枢尚未形成，当前判断仅适用于日线级别",
            ]
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
                close: base + 1.1
            )
        }
    }

    private static var signals: [Signal] {
        [
            Signal(type: .buy3, label: "三买", time: "2026-07-18", price: 208.34,
                   strength: .strong, isBuy: true,
                   description: "突破前中枢上沿后回踩不破，确认第三类买点。",
                   areaRatio: nil, confirmed: true),
            Signal(type: .buy2, label: "二买", time: "2026-06-25", price: 191.02,
                   strength: .medium, isBuy: true,
                   description: "一买后反弹回调不创新低，构成第二类买点。",
                   areaRatio: 0.72, confirmed: true),
            Signal(type: .sell1, label: "一卖", time: "2026-08-14", price: 219.60,
                   strength: .weak, isBuy: false,
                   description: "创新高但 MACD 面积明显缩小，出现盘整背驰。",
                   areaRatio: 0.58, confirmed: false),
        ]
    }
}

// Xcode 画布预览。分析结果态是这个 App 最复杂的界面，没有这些预览就只能
// 靠「起后端 → 登录 → 输代码 → 等分析」才能看一眼布局。

#Preview("结论") {
    ScrollView { ConclusionSection(analysis: PreviewMock.analysis).padding(14) }
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
#endif
