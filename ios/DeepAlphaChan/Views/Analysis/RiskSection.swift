import SwiftUI

/// 分段控件的「风险提示」段——原先折叠在整体分析卡片里，容易被当成结论的一部分
/// 顺手划过；现在单独成一个 tab，跟整体分析、买卖点并列，想看风险时才点进来，
/// 也不会被当成事实陈述的一部分。
///
/// 后端 caveats 已含「待确认结构」（caveats.extend(pending_notes)）。
struct RiskSection: View {
    let analysis: ChanAnalysis

    private var caveats: [String] { analysis.recommendation?.caveats ?? [] }

    var body: some View {
        SectionCard(title: L("风险提示"), systemImage: "exclamationmark.triangle.fill") {
            if caveats.isEmpty {
                Text(L("本次分析暂无需要特别注意的风险提示。"))
                    .font(AnalysisType.body)
                    .foregroundColor(Theme.textSecondary)
            } else {
                BulletList(items: caveats, color: Theme.segment)
            }
        }
    }
}
