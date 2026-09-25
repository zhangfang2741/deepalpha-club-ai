import SwiftUI

/// 未确认结构和其他风险分别呈现，避免后端 caveats 合并 pending_notes 后重复列出。
struct RiskSection: View {
    let analysis: ChanAnalysis

    var body: some View {
        VStack(spacing: 12) {
            SectionCard(title: L("先核对尚未确认的结构"), systemImage: "circle.dashed") {
                Text(L("与图表、雷达一致：虚线表示未确认，不表示看空。已确认也不代表后续价格必然按预期发展。"))
                    .font(AnalysisType.body)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                if AnalysisInterpretation.pendingNotes(analysis).isEmpty {
                    Text(L("本次数据未提供额外的待确认说明，请继续核对图上的虚线和买卖点状态。"))
                        .font(AnalysisType.body)
                        .foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    BulletList(items: AnalysisInterpretation.pendingNotes(analysis), color: Theme.textPrimary)
                }
            }
            SectionCard(title: L("其他风险与限制"), systemImage: "exclamationmark.triangle") {
                if AnalysisInterpretation.otherRisks(analysis).isEmpty {
                    Text(L("本次分析未提供额外风险条目，不代表没有风险。"))
                        .font(AnalysisType.body)
                        .foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    BulletList(items: AnalysisInterpretation.otherRisks(analysis), color: Theme.textPrimary)
                }
            }
            SectionCard(title: L("使用这些信息前"), systemImage: "checklist") {
                Text(L("先核对周期与中枢级别，再看信号是否确认。背驰表示力度减弱，不等于反转；历史信号也不等于当前仍有同样的条件。"))
                    .font(AnalysisType.body)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                WrapLayout(spacing: 16, lineSpacing: 4) {
                    AnalysisTermLink(term: "走势级别", color: Theme.textSecondary)
                    AnalysisTermLink(term: "背驰", color: Theme.divergence)
                }
            }
        }
    }
}
