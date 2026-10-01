import SwiftUI

/// 维度详情：顶部先用大白话讲清「这个维度看什么」和本股的关键事实，下面每项指标压成一行
/// （名称 + 全称、本股 vs 板块中位、位置条、等级），点开看大白话解读与算式。
struct QuantDimensionDetailView: View {
    let dimension: QuantDimension
    let research: QuantResearch

    @State private var selected: QuantMetric?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                header
                VStack(alignment: .leading, spacing: 6) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(L("各项指标")).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                        Spacer()
                        Text(L("点指标看大白话解读")).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    }
                    .padding(.horizontal, 4)
                    VStack(spacing: 0) {
                        ForEach(Array(dimension.allMetrics.enumerated()), id: \.element.key) { i, m in
                            if i > 0 { Divider().overlay(Theme.border) }
                            Button { selected = m } label: { QuantMetricRow(metric: m) }.buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 14)
                    .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
                }
                if let formula = dimension.formula {
                    DisclosureGroup(L("维度等级怎么来的")) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(L("维度分 = 各项指标板块百分位的平均"))
                                .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                            Text(formula)
                                .font(QuantTypography.emphasis.monospacedDigit())
                                .foregroundStyle(Theme.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 8)
                    }
                    .font(QuantTypography.body).foregroundStyle(Theme.textPrimary).tint(Theme.accent)
                    .padding(14)
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
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 14) {
                QuantGradeBlock(grade: dimension.isOK ? dimension.grade : nil, side: 56)
                VStack(alignment: .leading, spacing: 3) {
                    Text(dimension.name).font(QuantTypography.summary).foregroundStyle(Theme.textPrimary)
                    if let peer = research.peerGroup {
                        Text(peer.text).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    }
                }
                Spacer(minLength: 0)
            }
            if let fact = dimension.keyFact {
                Text(fact.text).font(QuantTypography.emphasis).foregroundStyle(Theme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            } else if let note = dimension.statusNote {
                Text(note).font(QuantTypography.body).foregroundStyle(Theme.segment)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let intro = QuantDimensionGuide.intro(dimension.key) {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "lightbulb").font(QuantTypography.metadata).foregroundStyle(Theme.accent)
                        .padding(.top, 2).accessibilityHidden(true)
                    Text(intro).font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                        .lineSpacing(3).fixedSize(horizontal: false, vertical: true)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
            }
        }
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
    }
}

/// 指标行：名称 + 全称一行，本股数值 vs 板块中位一行，下面一条位置条（中线 = 板块中位）。
struct QuantMetricRow: View {
    let metric: QuantMetric

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(metric.name).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                    if let subtitle = metric.fullNameSubtitle {
                        Text(subtitle).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                            .lineLimit(1)
                    }
                }
                Spacer(minLength: 8)
                VStack(alignment: .trailing, spacing: 2) {
                    Text(metric.displayValue).font(QuantTypography.value).monospacedDigit()
                        .foregroundStyle(Theme.textPrimary)
                    if let median = metric.sectorMedianDisplay {
                        Text(L("板块中位 %@", median)).font(QuantTypography.metadata).monospacedDigit()
                            .foregroundStyle(Theme.textSecondary)
                    }
                }
                QuantGradeBlock(grade: metric.grade, side: 34)
            }
            if let p = metric.percentile {
                QuantPercentileBar(percentile: p, color: QuantGradeStyle.color(metric.grade))
                    .accessibilityHidden(true)
            } else if let note = metric.statusNote {
                Text(note).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, 12)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint(L("查看大白话解读与计算"))
    }
}
