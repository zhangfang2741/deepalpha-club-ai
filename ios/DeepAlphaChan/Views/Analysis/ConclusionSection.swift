import SwiftUI

/// 分段控件的「结论」段：当前结构 + 操作倾向 + 待确认结构。
///
/// 从 SignalPanelView 拆出。买卖点单独成段，因为它是逐条明细，和这里的
/// 总体判断读法不同——混在一起时用户要滚过一长串信号才能看到风险提示。
struct ConclusionSection: View {
    let analysis: ChanAnalysis

    var body: some View {
        VStack(spacing: 12) {
            summaryCard
            if let rec = analysis.recommendation { recommendationCard(rec) }
            if !analysis.pendingNotes.isEmpty { pendingCard }
        }
    }

    private var summaryCard: some View {
        SectionCard(title: "当前结构", systemImage: "chart.xyaxis.line") {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Chip(text: SignalFormatting.trendLabel(analysis.currentTrend),
                         color: SignalFormatting.trendColor(analysis.currentTrend))
                    Chip(text: "\(analysis.barsCount) 根K线", color: Theme.textSecondary)
                }
                Text(analysis.summary)
                    .font(.caption)
                    .foregroundColor(Theme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func recommendationCard(_ rec: Recommendation) -> some View {
        SectionCard(title: "操作倾向", systemImage: "target") {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text(rec.actionLabel)
                        .font(.title3.bold())
                        .foregroundColor(SignalFormatting.biasColor(rec.bias))
                    Spacer()
                    Chip(text: SignalFormatting.biasLabel(rec.bias),
                         color: SignalFormatting.biasColor(rec.bias))
                }
                if !rec.reasons.isEmpty {
                    BulletList(title: "依据", items: rec.reasons, color: Theme.textPrimary)
                }
                if !rec.caveats.isEmpty {
                    BulletList(title: "风险提示", items: rec.caveats, color: Theme.segment)
                }
            }
        }
    }

    private var pendingCard: some View {
        SectionCard(title: "待确认结构", systemImage: "hourglass") {
            VStack(alignment: .leading, spacing: 6) {
                ForEach(analysis.pendingNotes, id: \.self) { note in
                    HStack(alignment: .top, spacing: 6) {
                        Text("•").foregroundColor(Theme.textSecondary)
                        Text(note).font(.caption).foregroundColor(Theme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }
}
