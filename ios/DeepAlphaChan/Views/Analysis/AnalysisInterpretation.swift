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
}
