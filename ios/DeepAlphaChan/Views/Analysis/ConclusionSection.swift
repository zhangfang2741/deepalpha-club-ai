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
            if let narrative = analysis.narrative { narrativeCard(narrative) }
            summaryCard
            if let rec = analysis.recommendation { recommendationCard(rec) }
            if !analysis.pendingNotes.isEmpty { pendingCard }
        }
    }

    /// 大白话形态解读：把缠论结构翻译成「市场此刻在做什么」，放在最前面，
    /// 让看不懂笔/中枢/背驰的普通用户也能先读懂一句话结论。
    private func narrativeCard(_ n: MarketNarrative) -> some View {
        CollapsibleCard(title: "形态解读", systemImage: "text.magnifyingglass",
                        accessoryChip: (n.phaseLabel, SignalFormatting.phaseColor(n.phase))) {
            VStack(alignment: .leading, spacing: 10) {
                Text(n.headline)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Theme.textPrimary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                if !n.details.isEmpty {
                    Divider().overlay(Theme.border)
                    VStack(alignment: .leading, spacing: 7) {
                        ForEach(n.details, id: \.self) { line in
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Circle()
                                    .fill(Theme.textSecondary.opacity(0.55))
                                    .frame(width: 4, height: 4)
                                    .frame(width: 6, alignment: .center)
                                    .offset(y: -4)
                                Text(line)
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
    }

    private var summaryCard: some View {
        CollapsibleCard(title: "当前结构", systemImage: "chart.xyaxis.line",
                        accessoryChip: (SignalFormatting.trendLabel(analysis.currentTrend),
                                        SignalFormatting.trendColor(analysis.currentTrend))) {
            VStack(alignment: .leading, spacing: 10) {
                Chip(text: "\(analysis.barsCount) 根 K 线", color: Theme.textSecondary)
                Text(analysis.summary)
                    .font(ConclusionType.body)
                    // 与「待确认结构」正文同为 textSecondary：都是详情正文，
                    // 统一成次要色，把 textPrimary 留给标题/结论那一层。
                    .foregroundColor(Theme.textSecondary)
                    .lineSpacing(ConclusionType.bodyLineSpacing)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func recommendationCard(_ rec: Recommendation) -> some View {
        CollapsibleCard(title: "操作倾向", systemImage: "target",
                        accessoryChip: (SignalFormatting.biasLabel(rec.bias),
                                        SignalFormatting.biasColor(rec.bias))) {
            VStack(alignment: .leading, spacing: 14) {
                // 结论本身单独一行：它是这张卡的答案，和下面的「依据/风险提示」
                // 是两个层次，挨着排会混成一团。
                Text(rec.actionLabel)
                    .font(.system(size: 22, weight: .bold))
                    .foregroundColor(SignalFormatting.biasColor(rec.bias))
                    .fixedSize(horizontal: false, vertical: true)

                if !rec.reasons.isEmpty || !rec.caveats.isEmpty {
                    Divider().overlay(Theme.border)
                }

                if !rec.reasons.isEmpty {
                    // 依据是详情正文，与「待确认结构」一致用 textSecondary
                    BulletList(title: "依据", items: rec.reasons, color: Theme.textSecondary)
                }
                if !rec.caveats.isEmpty {
                    BulletList(title: "风险提示", items: rec.caveats, color: Theme.segment)
                }
            }
        }
    }

    private var pendingCard: some View {
        CollapsibleCard(title: "待确认结构", systemImage: "hourglass",
                        accessoryChip: ("\(analysis.pendingNotes.count) 项", Theme.segment)) {
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
