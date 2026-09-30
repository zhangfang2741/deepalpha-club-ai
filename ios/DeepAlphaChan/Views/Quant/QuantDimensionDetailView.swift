import SwiftUI

/// 维度详情（从量化研究首页点维度卡片进入）：顶部展开维度分算式，下面按组列出每项指标——
/// 本股 / 板块中位 / 差异、百分位条、单项等级；点指标弹出指标详情 sheet。
struct QuantDimensionDetailView: View {
    let dimension: QuantDimension
    let research: QuantResearch

    @State private var selected: QuantMetric?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                header
                ForEach(dimension.groups) { group in
                    QuantSectionHeader(text: group.name)
                    VStack(spacing: 0) {
                        ForEach(Array(group.metrics.enumerated()), id: \.element.key) { i, m in
                            if i > 0 { Divider().background(Theme.border) }
                            Button { selected = m } label: { row(m) }.buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 14)
                    .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
                }
                Text(research.disclaimer)
                    .font(.caption2).foregroundStyle(Theme.textSecondary)
                    .multilineTextAlignment(.center).frame(maxWidth: .infinity).padding(.top, 6)
            }
            .padding(.horizontal, Theme.contentHInset)
            .padding(.vertical, Theme.contentVInset)
        }
        .background(Theme.background)
        .navigationTitle("\(research.symbol) · \(dimension.name)")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $selected) { m in
            QuantMetricSheet(metric: m, research: research)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(dimension.name).font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.textPrimary)
                Spacer()
                QuantGradeBadge(grade: dimension.grade, size: 17)
            }
            Text(dimension.description).font(.footnote).foregroundStyle(Theme.textSecondary)
            if let formula = dimension.formula {
                VStack(alignment: .leading, spacing: 4) {
                    Text(L("维度分 = 各项指标板块百分位的平均"))
                        .font(.caption).foregroundStyle(Theme.textSecondary)
                    Text(formula)
                        .font(.system(size: 14, weight: .semibold).monospacedDigit())
                        .foregroundStyle(Theme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
            } else if let note = dimension.statusNote {
                Text(note).font(.footnote).foregroundStyle(Theme.segment)
            }
            if let peer = research.peerGroup {
                Text(peer.text).font(.caption2).foregroundStyle(Theme.textSecondary)
            }
        }
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
    }

    private func row(_ m: QuantMetric) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .firstTextBaseline) {
                Text(m.name).font(.subheadline.weight(.medium)).foregroundStyle(Theme.textPrimary)
                Spacer(minLength: 8)
                Text(m.displayValue).font(.subheadline.monospacedDigit()).foregroundStyle(Theme.textPrimary)
                if let median = m.sectorMedianDisplay {
                    Text("/ \(median)").font(.caption.monospacedDigit()).foregroundStyle(Theme.textSecondary)
                }
                QuantGradeBadge(grade: m.grade, size: 11)
            }
            if let p = m.percentile {
                QuantPercentileBar(percentile: p, color: QuantGradeStyle.color(m.grade))
                HStack {
                    Text(L("第 %@ 百分位", String(format: "%.0f", p)))
                    if let diff = m.diffToMedianPct {
                        Text(L("较板块中位 %@", String(format: "%+.0f%%", diff)))
                    }
                    Spacer()
                }
                .font(.caption2).foregroundStyle(Theme.textSecondary)
            } else if let note = m.statusNote {
                Text(note).font(.caption2).foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, 10)
        .contentShape(Rectangle())
    }
}
