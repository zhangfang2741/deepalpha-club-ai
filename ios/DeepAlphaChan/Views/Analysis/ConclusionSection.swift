import SwiftUI

/// 分段控件的「结论」段。
///
/// 精简为两张卡：
/// - 形态解读：大白话讲当前市场在做什么，末尾并入一行精简的结构统计（原「当前结构」
///   那段冗长的技术描述被这行取代）；
/// - 操作倾向：操作结论 + 依据 + 风险提示（后端 caveats 已含「待确认结构」，故不再
///   单列一张待确认卡，避免重复）。
///
/// 字号统一走 ConclusionType 的三级（见 SignalFormatting.swift）。
struct ConclusionSection: View {
    let analysis: ChanAnalysis

    var body: some View {
        VStack(spacing: 12) {
            formCard
            if let rec = analysis.recommendation { recommendationCard(rec) }
        }
    }

    /// 一行精简结构统计，取代原「当前结构」那段长技术描述。
    private var structureStats: String {
        let pivots = analysis.strokePivots.count + analysis.segmentPivots.count
        return "\(analysis.barsCount) 根K线 · \(analysis.strokes.count) 笔 · "
            + "\(analysis.segments.count) 线段 · \(pivots) 中枢 · \(analysis.signals.count) 买卖点"
    }

    /// 形态解读（含结构统计）。默认展开——它是这张页面最该先读的一句话结论。
    private var formCard: some View {
        let n = analysis.narrative
        let chip: (String, Color) = n != nil
            ? (n!.phaseLabel, SignalFormatting.phaseColor(n!.phase))
            : (SignalFormatting.trendLabel(analysis.currentTrend),
               SignalFormatting.trendColor(analysis.currentTrend))

        return CollapsibleCard(title: "形态解读", systemImage: "text.magnifyingglass",
                               accessoryChip: chip, defaultExpanded: true) {
            VStack(alignment: .leading, spacing: 10) {
                if let n {
                    Text(n.headline)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(Theme.textPrimary)
                        .lineSpacing(4)
                        .fixedSize(horizontal: false, vertical: true)

                    if !n.details.isEmpty {
                        Divider().overlay(Theme.border)
                        VStack(alignment: .leading, spacing: 7) {
                            ForEach(n.details, id: \.self) { line in
                                bullet(line, color: Theme.textSecondary)
                            }
                        }
                    }
                } else {
                    // 结构没成形（笔太少）时没有大白话解读，退回后端摘要
                    Text(analysis.summary)
                        .font(ConclusionType.body)
                        .foregroundColor(Theme.textSecondary)
                        .lineSpacing(ConclusionType.bodyLineSpacing)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Divider().overlay(Theme.border)
                Text(structureStats)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
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
                    BulletList(title: "依据", items: rec.reasons, color: Theme.textSecondary)
                }
                if !rec.caveats.isEmpty {
                    // 风险提示已包含「待确认结构」（后端 caveats.extend(pending_notes)）
                    BulletList(title: "风险提示", items: rec.caveats, color: Theme.segment)
                }
            }
        }
    }

    /// 项目符号一行（与 BulletList 内部样式一致，供 details 复用）。
    private func bullet(_ text: String, color: Color) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Circle()
                .fill(color.opacity(0.55))
                .frame(width: 4, height: 4)
                .frame(width: 6, alignment: .center)
                .offset(y: -4)
            Text(text)
                .font(ConclusionType.body)
                .foregroundColor(color)
                .lineSpacing(ConclusionType.bodyLineSpacing)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
