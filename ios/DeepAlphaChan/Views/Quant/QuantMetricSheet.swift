import SwiftUI

/// 指标详情（全屏 sheet）：定义 → 带真实数字的算式 → 本股在板块分布中的位置（P10 ~ P90）
/// → 「位置 → 百分位 → 等级」推导 → 原始数据与各自的时间点。让每个等级都能追到原始数据。
struct QuantMetricSheet: View {
    let metric: QuantMetric
    let research: QuantResearch
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                QuantMetricDetailContent(metric: metric, research: research)
            }
            .background(Theme.background)
            .navigationTitle(L("指标解读"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("完成")) { dismiss() }
                }
            }
        }
    }
}

/// 指标详情的内容本体（不含滚动容器，便于离屏渲染验收）。
struct QuantMetricDetailContent: View {
    let metric: QuantMetric
    let research: QuantResearch

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            heroHeader
            if let pos = metric.positionText {
                Text(pos).font(QuantTypography.emphasis).foregroundStyle(Theme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let itp = metric.interpretation, !itp.what.isEmpty {
                interpretationBlock(itp)
            }
            if metric.interpretation == nil && !metric.description.isEmpty {
                Text(metric.description).font(QuantTypography.body).foregroundStyle(Theme.textPrimary.opacity(0.85))
                    .lineSpacing(3).fixedSize(horizontal: false, vertical: true)
            }
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 10) {
                    pill(L("方向"), metric.lowerBetter ? L("越低排名越靠前") : L("越高排名越靠前"))
                    if let g = metric.grade, !g.isEmpty { pill(L("档位"), g) }
                }
                pill(L("方向"), metric.lowerBetter ? L("越低排名越靠前") : L("越高排名越靠前"))
            }
            if let f = metric.formula {
                calcCard(f)
            } else {
                box(title: L("如何计算")) {
                    Text(metric.interpretation?.calculation ?? metric.description)
                        .font(QuantTypography.body).foregroundStyle(Theme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(L("当前数据不足，暂无可代入的计算结果。"))
                        .font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                }
            }
            if let note = metric.statusNote {
                Text(note).font(QuantTypography.body).foregroundStyle(Theme.segment)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let dist = metric.distribution, let peer = research.peerGroup {
                Text(L("在%@板块 %lld 家公司中的位置", peer.sectorName, peer.sampleSize))
                    .font(QuantTypography.emphasis).foregroundStyle(Theme.textSecondary)
                DistributionStrip(distribution: dist, value: metric.value, valueLabel: metric.displayValue,
                                  symbol: research.symbol, lowerBetter: metric.lowerBetter,
                                  isPercent: metric.displayValue.hasSuffix("%"))
            }
            if metric.positionText != nil {
                DisclosureGroup(L("等级是怎么算的？")) {
                    Text(L("分档：≥93 A+ · ≥86 A · ≥80 A- · … · <20 F"))
                        .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                 .font(QuantTypography.body).tint(Theme.accent)
            }
            DisclosureGroup(L("术语速查")) {
                Text(L("TTM：最近 12 个月实际值\nFWD：基于分析师预期\nNTM：未来 12 个月；本页按财年剩余时间加权\nEPS：每股收益\nEBIT：息税前利润\nEBITDA：息税折旧摊销前利润\nEV：本页按市值 + 负债 − 现金计算\n百分位：按指标优劣方向换算的相对排名，不是收益率"))
                    .font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                    .lineSpacing(6).frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.top, 8)
            }
             .font(QuantTypography.body).tint(Theme.accent)


        }
        .padding(18)
    }

    private var heroHeader: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                Text(metric.name).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                Spacer(minLength: 8)
                QuantGradeBadge(grade: metric.grade)
            }
            Text(research.symbol).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
            Text(metric.displayValue).font(QuantTypography.summary).monospacedDigit()
                .foregroundStyle(Theme.textPrimary)
            if let median = metric.sectorMedianDisplay {
                Text(L("板块中位") + "  " + median)
                     .font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
            }
        }
        .padding(20).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 20))
    }

    private func interpretationBlock(_ itp: QuantMetricInterpretation) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "lightbulb.fill").font(QuantTypography.metadata)
                Text(L("价值投资视角")).font(QuantTypography.metadata.weight(.semibold))
            }
            .foregroundStyle(Theme.accent)
            Text(itp.what).font(QuantTypography.body).foregroundStyle(Theme.textPrimary.opacity(0.92))
                .lineSpacing(4).fixedSize(horizontal: false, vertical: true)
            if !itp.role.isEmpty {
                HStack(alignment: .top, spacing: 6) {
                    Text(L("如何理解"))
                        .font(QuantTypography.metadata.weight(.semibold))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Theme.surfaceAlt, in: Capsule())
                        .foregroundStyle(Theme.textSecondary)
                    Text(itp.role).font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if !itp.threshold.isEmpty {
                Divider().background(Theme.border)
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill").font(QuantTypography.metadata)
                        .foregroundStyle(Theme.segment)
                    Text(itp.threshold).font(QuantTypography.body).foregroundStyle(Theme.textPrimary.opacity(0.9))
                        .lineSpacing(2).fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(14).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.accent.opacity(0.3)))
    }

    private func pill(_ title: String, _ text: String) -> some View {
        HStack(spacing: 6) {
            Text(title).font(QuantTypography.metadata.weight(.semibold)).foregroundStyle(Theme.textSecondary)
            Text(text).font(QuantTypography.metadata).foregroundStyle(Theme.textPrimary)
        }
        .padding(.horizontal, 10).padding(.vertical, 6)
        .background(Theme.surfaceAlt, in: Capsule())
    }

    private func calcCard(_ f: QuantFormula) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(L("如何计算")).font(QuantTypography.metadata.weight(.semibold)).foregroundStyle(Theme.textSecondary)
            if let calculation = metric.interpretation?.calculation {
                Text(calculation).font(QuantTypography.body).foregroundStyle(Theme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(L("代入本股数据")).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    .padding(.top, 8)
            }
            Text(f.expression).font(QuantTypography.body.monospacedDigit())
                .foregroundStyle(Theme.textPrimary).fixedSize(horizontal: false, vertical: true)
            if !f.inputs.isEmpty {
                VStack(spacing: 0) {
                    ForEach(f.inputs) { i in
                        Divider().background(Theme.border).padding(.vertical, 4)
                        HStack(alignment: .firstTextBaseline) {
                            Text(i.label).foregroundStyle(Theme.textSecondary)
                            Spacer(minLength: 8)
                            VStack(alignment: .trailing, spacing: 2) {
                                Text(i.value).monospacedDigit().foregroundStyle(Theme.textPrimary)
                                if let n = i.note {
                                    Text(n).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                                        .multilineTextAlignment(.trailing)
                                }
                            }
                        }
                        .font(QuantTypography.body)
                    }
                }
                .padding(.top, 6)
            }
        }
        .padding(14).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
    }

    private func box<C: View>(title: String?, @ViewBuilder _ content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if let title { Text(title).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary) }
            content()
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
    }
}

/// 板块分布条：P10 / P25 / 中位 / P75 / P90 刻度 + 本股位置（超出 P10~P90 时贴边）。
struct DistributionStrip: View {
    let distribution: [String: Double]
    let value: Double?
    let valueLabel: String
    let symbol: String
    let lowerBetter: Bool
    /// 百分比类指标（增速、利润率、涨幅）的刻度按百分比显示；倍数类按数值显示。
    let isPercent: Bool

    private var ticks: [(String, Double)] {
        [("P10", "p10"), ("P25", "p25"), (L("中位"), "p50"), ("P75", "p75"), ("P90", "p90")]
            .compactMap { name, key in distribution[key].map { (name, $0) } }
    }

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let lo = ticks.first?.1 ?? 0
            let hi = ticks.last?.1 ?? 1
            let span = max(hi - lo, 1e-9)
            let x: (Double) -> CGFloat = { v in w * 0.08 + (w * 0.84) * CGFloat((v - lo) / span) }
            ZStack(alignment: .topLeading) {
                LinearGradient(colors: lowerBetter ? [Theme.up, Theme.surfaceAlt, Theme.down]
                                                   : [Theme.down, Theme.surfaceAlt, Theme.up],
                               startPoint: .leading, endPoint: .trailing)
                    .frame(height: 3).clipShape(Capsule()).opacity(0.75).offset(y: 22)
                ForEach(ticks, id: \.0) { name, v in
                    VStack(spacing: 1) {
                        Text(Self.short(v, isPercent: isPercent)).font(.system(size: 10).monospacedDigit())
                        Text(name).font(.system(size: 9))
                    }
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize()
                    .position(x: x(v), y: 44)
                }
                if let value {
                    let px = min(max(x(value), 2), w - 2)
                    Rectangle().fill(Theme.textPrimary).frame(width: 1.5, height: 16)
                        .position(x: px, y: 23.5)
                    Text("\(symbol) \(valueLabel)")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(Theme.textPrimary)
                        .fixedSize()
                        .position(x: min(max(px, 40), w - 40), y: 6)
                }
            }
        }
        .frame(height: 58)
    }

    static func short(_ v: Double, isPercent: Bool) -> String {
        if isPercent { return String(format: "%.0f%%", v * 100) }
        let a = abs(v)
        if a >= 100 { return String(format: "%.0f", v) }
        if a >= 10 { return String(format: "%.1f", v) }
        return String(format: "%.2f", v)
    }
}
