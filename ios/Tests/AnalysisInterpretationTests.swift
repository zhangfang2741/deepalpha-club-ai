import Foundation
import SwiftUI

// 独立测试只验证呈现数据的归并规则，不依赖 App Bundle 的翻译资源。
func L(_ key: String, _ arguments: CVarArg...) -> String {
    String(format: key, arguments: arguments)
}

@main
struct AnalysisInterpretationTests {
    static func main() throws {
        precondition(HeadlineHighlighter.highlight("背驰").runs.first?.foregroundColor == Theme.divergence)
        precondition(HeadlineHighlighter.highlight("三买").runs.first?.foregroundColor == Theme.up)
        precondition(HeadlineHighlighter.highlight("一卖").runs.first?.foregroundColor == Theme.down)
        precondition(HeadlineHighlighter.highlight("3rd Buy").runs.first?.foregroundColor == Theme.up)
        precondition(HeadlineHighlighter.highlight("线段").runs.first?.foregroundColor == Theme.segment)
        precondition(HeadlineHighlighter.highlight("Segment").runs.first?.foregroundColor == Theme.segment)
        precondition(HeadlineHighlighter.highlight("pivot").runs.first?.foregroundColor == Theme.pivotFill)
        precondition(SignalFormatting.strengthDepth("strong") > SignalFormatting.strengthDepth("medium"))
        precondition(SignalFormatting.strengthDepth("medium") > SignalFormatting.strengthDepth("weak"))
        precondition(Theme.pivotPhaseColor("divergence_turn") == Theme.divergence)

        let analysis = try fixture(pending: [" 末笔未确认 ", "末笔未确认", "\n"],
                                   caveats: ["末笔未确认", "周期不匹配", " 周期不匹配 ", ""])
        precondition(AnalysisInterpretation.pendingNotes(analysis) == ["末笔未确认"])
        precondition(AnalysisInterpretation.otherRisks(analysis) == ["周期不匹配"])
        precondition(AnalysisInterpretation.riskCount(analysis) == 2, "Tab 数量必须等于去重后的可见条目")

        let noRecommendation = try fixture(pending: ["末笔未确认"], caveats: nil)
        precondition(AnalysisInterpretation.riskCount(noRecommendation) == 1, "缺少 recommendation 时仍须显示待确认结构")
        let empty = try fixture(pending: [], caveats: nil)
        precondition(AnalysisInterpretation.riskCount(empty) == 0)
        let caveatsOnly = try fixture(pending: [], caveats: ["观察中枢", "观察中枢", "数据不足"])
        precondition(AnalysisInterpretation.otherRisks(caveatsOnly) == ["观察中枢", "数据不足"], "保留首次出现的顺序")
        precondition(AnalysisInterpretation.branchExplanation("type2").contains("不能仅凭"))
        precondition(AnalysisInterpretation.branchExplanation("type3").contains("不等于信号已确认"))
    }

    private static func fixture(pending: [String], caveats: [String]?) throws -> ChanAnalysis {
        var object: [String: Any] = [
            "symbol": "TEST", "bars_count": 0, "merged_candles": [], "fractals": [],
            "strokes": [], "segments": [], "stroke_pivots": [], "segment_pivots": [],
            "signals": [], "current_trend": "range", "summary": "测试数据",
            "pending_notes": pending, "structure_layers": []
        ]
        if let caveats {
            object["recommendation"] = ["action": "wait", "action_label": "观察", "bias": "neutral",
                                        "reasons": [], "caveats": caveats] as [String: Any]
        }
        return try JSONDecoder().decode(ChanAnalysis.self, from: JSONSerialization.data(withJSONObject: object))
    }
}
