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
                    .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
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
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(dimension.name).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                Spacer()
                QuantGradeBadge(grade: dimension.grade)
            }
            if let fact = dimension.keyFact {
                Text(fact.text).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(dimension.description).font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
            if let formula = dimension.formula {
                DisclosureGroup(L("展开评分计算")) {
                    Text(L("维度分 = 各项指标板块百分位的平均"))
                        .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    Text(formula)
                        .font(QuantTypography.emphasis.monospacedDigit())
                        .foregroundStyle(Theme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
            } else if let note = dimension.statusNote {
                Text(note).font(QuantTypography.body).foregroundStyle(Theme.segment)
            }
            if let peer = research.peerGroup {
                Text(peer.text).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
            }
        }
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
    }

    private func row(_ m: QuantMetric) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                Text(m.name).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                Spacer(minLength: 8)
                QuantGradeBadge(grade: m.grade)
            }
            Text(m.interpretation?.what ?? m.description)
                .font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(alignment: .top, spacing: 24) {
                valueColumn(L("本股"), value: m.displayValue, prominent: true)
                if let median = m.sectorMedianDisplay {
                    valueColumn(L("板块中位"), value: median, prominent: false)
                }
                Spacer(minLength: 0)
            }
            if let p = m.percentile {
                QuantPercentileBar(percentile: p, color: QuantGradeStyle.color(m.grade))
                Text(L("第 %@ 百分位", String(format: "%.0f", p)))
                    .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
            }
            if let note = m.statusNote {
                Text(note).font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Label(L("查看计算与价值解读"), systemImage: "info.circle")
                .font(QuantTypography.metadata).foregroundStyle(Theme.accent)
        }
        .padding(.vertical, 18)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint(L("查看计算与价值解读"))
    }

    private func valueColumn(_ title: String, value: String, prominent: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
            Text(value).font(prominent ? QuantTypography.value : QuantTypography.body)
                .monospacedDigit().foregroundStyle(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
