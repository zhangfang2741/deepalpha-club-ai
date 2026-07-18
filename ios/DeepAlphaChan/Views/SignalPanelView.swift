import SwiftUI

/// 结论摘要 + 操作建议 + 买卖点列表。
struct SignalPanelView: View {
    let analysis: ChanAnalysis

    var body: some View {
        VStack(spacing: 12) {
            summaryCard
            if let rec = analysis.recommendation { recommendationCard(rec) }
            signalsCard
            if !analysis.pendingNotes.isEmpty { pendingCard }
        }
    }

    private var summaryCard: some View {
        SectionCard(title: "当前结构", systemImage: "chart.xyaxis.line") {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Chip(text: trendLabel, color: trendColor)
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
                        .foregroundColor(biasColor(rec.bias))
                    Spacer()
                    Chip(text: biasLabel(rec.bias), color: biasColor(rec.bias))
                }
                if !rec.reasons.isEmpty {
                    bulletList(title: "依据", items: rec.reasons, color: Theme.textPrimary)
                }
                if !rec.caveats.isEmpty {
                    bulletList(title: "风险提示", items: rec.caveats, color: Theme.segment)
                }
            }
        }
    }

    private var signalsCard: some View {
        SectionCard(title: "买卖点", systemImage: "flag.fill") {
            if analysis.signals.isEmpty {
                Text("当前区间未识别到明确买卖点")
                    .font(.subheadline).foregroundColor(Theme.textSecondary)
            } else {
                VStack(spacing: 8) {
                    ForEach(analysis.signals) { sig in signalRow(sig) }
                }
            }
        }
    }

    private func signalRow(_ sig: Signal) -> some View {
        HStack(alignment: .top, spacing: 10) {
            RoundedRectangle(cornerRadius: 3)
                .fill(sig.isBuy ? Theme.up : Theme.down)
                .frame(width: 4)
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(sig.label).font(.subheadline.bold())
                        .foregroundColor(sig.isBuy ? Theme.up : Theme.down)
                    Chip(text: strengthLabel(sig.strength), color: strengthColor(sig.strength))
                    if !sig.confirmed { Chip(text: "未确认", color: Theme.textSecondary) }
                    Spacer()
                    Text(sig.time).font(.caption).foregroundColor(Theme.textSecondary)
                }
                Text(sig.description).font(.caption).foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 12) {
                    Text("价位 \(String(format: "%.2f", sig.price))")
                    if let ar = sig.areaRatio {
                        Text("面积比 \(String(format: "%.2f", ar))")
                    }
                }
                .font(.caption2).foregroundColor(Theme.textSecondary)
            }
        }
        .padding(10)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 8))
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

    private func bulletList(title: String, items: [String], color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption.bold()).foregroundColor(Theme.textSecondary)
            ForEach(items, id: \.self) { item in
                HStack(alignment: .top, spacing: 6) {
                    Text("•").foregroundColor(color)
                    Text(item).font(.caption).foregroundColor(color)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    // MARK: - 文案/配色映射

    private var trendLabel: String {
        switch analysis.currentTrend {
        case "up": return "上涨趋势"
        case "down": return "下跌趋势"
        case "oscillation", "range": return "震荡整理"
        default: return analysis.currentTrend
        }
    }
    private var trendColor: Color {
        switch analysis.currentTrend {
        case "up": return Theme.up
        case "down": return Theme.down
        default: return Theme.segment
        }
    }
    private func biasLabel(_ b: String) -> String {
        switch b { case "bullish": return "偏多"; case "bearish": return "偏空"; default: return "中性" }
    }
    private func biasColor(_ b: String) -> Color {
        switch b { case "bullish": return Theme.up; case "bearish": return Theme.down; default: return Theme.segment }
    }
    private func strengthLabel(_ s: Signal.Strength) -> String {
        switch s { case .strong: return "强"; case .medium: return "中"; case .weak: return "弱" }
    }
    private func strengthColor(_ s: Signal.Strength) -> Color {
        switch s { case .strong: return Theme.accent; case .medium: return Theme.segment; case .weak: return Theme.textSecondary }
    }
}
