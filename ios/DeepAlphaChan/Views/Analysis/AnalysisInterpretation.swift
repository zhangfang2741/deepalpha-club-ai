import Foundation

/// 只整理已有分析事实，不另行推导交易信号。
enum AnalysisInterpretation {
    static func uniqueNotes(_ notes: [String]) -> [String] {
        var seen: Set<String> = []
        return notes.compactMap { note in
            let value = note.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !value.isEmpty, seen.insert(value).inserted else { return nil }
            return value
        }
    }

    static func pendingNotes(_ analysis: ChanAnalysis) -> [String] {
        uniqueNotes(analysis.pendingNotes)
    }

    static func otherRisks(_ analysis: ChanAnalysis) -> [String] {
        let pending = Set(pendingNotes(analysis))
        return uniqueNotes(analysis.recommendation?.caveats ?? []).filter { !pending.contains($0) }
    }

    /// 每个风险类别最多展示这么多条——列表太长读起来是负担，保留最靠前（后端已按
    /// 从细到粗的结构粒度排列）的几条就够。`otherRisks` 的去重仍基于完整的
    /// `pendingNotes`，不受这个截断影响，避免被截掉的条目又在另一栏重复出现。
    static let riskDisplayLimit = 2

    static func displayedPendingNotes(_ analysis: ChanAnalysis) -> [String] {
        Array(pendingNotes(analysis).prefix(riskDisplayLimit))
    }

    static func displayedOtherRisks(_ analysis: ChanAnalysis) -> [String] {
        Array(otherRisks(analysis).prefix(riskDisplayLimit))
    }

    static func riskCount(_ analysis: ChanAnalysis) -> Int {
        displayedPendingNotes(analysis).count + displayedOtherRisks(analysis).count
    }

    static func stageExplanation(_ phase: String) -> String {
        switch phase {
        case "pivot_forming": return L("连续走势的重叠区间构成中枢，先定位上下沿。")
        case "pivot_oscillating": return L("价格围绕中枢反复，观察区间是否继续延伸。")
        case "leaving": return L("价格离开中枢，观察后续回抽；离开本身不等于三类信号。")
        case "retrace_confirmed": return L("回抽结构已确认，再核对落点与中枢的关系及具体买卖点条件。")
        case "divergence_turn": return L("创新高或新低时力度减弱，提示可能转折，不保证反转。")
        default: return L("结合当前结构与确认状态理解这一阶段。")
        }
    }
}
