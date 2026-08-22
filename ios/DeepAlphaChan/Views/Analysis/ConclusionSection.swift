import SwiftUI

/// 分段控件的「结论」段：当前结构 + 操作倾向 + 待确认结构。
///
/// 从 SignalPanelView 拆出。买卖点单独成段，因为它是逐条明细，和这里的
/// 总体判断读法不同——混在一起时用户要滚过一长串信号才能看到风险提示。
///
/// 字号统一走 ConclusionType 的三级（标题 17 / 正文 15 / 段内标签 13 加重），
/// 见 SignalFormatting.swift 里的说明。
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
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 6) {
                    Chip(text: SignalFormatting.trendLabel(analysis.currentTrend),
                         color: SignalFormatting.trendColor(analysis.currentTrend))
                    Chip(text: "\(analysis.barsCount) 根 K 线", color: Theme.textSecondary)
                }
                Text(analysis.summary)
                    .font(ConclusionType.body)
                    .foregroundColor(Theme.textPrimary)
                    .lineSpacing(ConclusionType.bodyLineSpacing)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func recommendationCard(_ rec: Recommendation) -> some View {
        SectionCard(title: "操作倾向", systemImage: "target") {
            VStack(alignment: .leading, spacing: 14) {
                // 结论本身单独一行并加分隔线：它是这张卡的答案，
                // 和下面的「依据/风险提示」是两个层次，挨着排会混成一团。
                HStack(alignment: .firstTextBaseline) {
                    Text(rec.actionLabel)
                        .font(.system(size: 22, weight: .bold))
                        .foregroundColor(SignalFormatting.biasColor(rec.bias))
                    Spacer()
                    Chip(text: SignalFormatting.biasLabel(rec.bias),
                         color: SignalFormatting.biasColor(rec.bias))
                }

                if !rec.reasons.isEmpty || !rec.caveats.isEmpty {
                    Divider().overlay(Theme.border)
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
            VStack(alignment: .leading, spacing: 7) {
                ForEach(analysis.pendingNotes, id: \.self) { note in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Circle()
                            .fill(Theme.textSecondary.opacity(0.55))
                            .frame(width: 4, height: 4)
                            .frame(width: 6, alignment: .center)
                            .offset(y: -4)
                        Text(note)
                            .font(ConclusionType.body)
                            .foregroundColor(Theme.textSecondary)
                            .lineSpacing(ConclusionType.bodyLineSpacing)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }
}
