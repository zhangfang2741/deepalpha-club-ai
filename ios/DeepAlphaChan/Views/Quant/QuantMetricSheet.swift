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
/// 顺序按「先懂再看再算」：是什么（大白话）→ 本股在板块里的位置 → 高低怎么看 → 怎么算（折叠）。
struct QuantMetricDetailContent: View {
    let metric: QuantMetric
    let research: QuantResearch

    private var itp: QuantMetricInterpretation? { metric.interpretation }
    /// 新版响应有大白话；旧缓存回退到口径描述。
    private var plain: String? { itp?.plain.flatMap { $0.isEmpty ? nil : $0 } }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            heroHeader
            plainBlock
            positionBlock
            readingBlock
            calculationGroup
        }
        .padding(18)
    }

    private var heroHeader: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(metric.name).font(QuantTypography.summary).foregroundStyle(Theme.textPrimary)
                    if let full = itp?.fullName, !full.isEmpty, full != metric.name {
                        Text(full).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 8)
                QuantGradeBlock(grade: metric.grade, side: 48)
                    .quantExplain(L("「%@」等级怎么来的", metric.name)) {
                        QuantMetricGradeExplanation(metric: metric, peer: research.peerGroup)
                    }
            }
            HStack(alignment: .firstTextBaseline, spacing: 14) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(research.symbol).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    Text(metric.displayValue).font(.system(size: 30, weight: .bold, design: .rounded)).monospacedDigit()
                        .foregroundStyle(Theme.textPrimary)
                }
                if let median = metric.sectorMedianDisplay {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 3) {
                            Text(L("板块中位")).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                            QuantInfoMark()
                        }
                        Text(median).font(QuantTypography.value).monospacedDigit().foregroundStyle(Theme.textSecondary)
                    }
                    .quantExplain(L("板块中位是什么")) { QuantMedianExplanation(metric: metric, research: research) }
                }
                Spacer(minLength: 0)
            }
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 18))
    }

    /// 一句话看懂：大白话释义（旧响应回退到口径描述）。
    @ViewBuilder
    private var plainBlock: some View {
        let text = plain ?? itp?.what ?? metric.description
        if !text.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Label(L("一句话看懂"), systemImage: "lightbulb.fill")
                    .font(QuantTypography.metadata.weight(.semibold)).foregroundStyle(Theme.accent)
                Text(text).font(QuantTypography.body).foregroundStyle(Theme.textPrimary.opacity(0.92))
                    .lineSpacing(4).fixedSize(horizontal: false, vertical: true)
            }
            .padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.accent.opacity(0.3)))
        }
    }

    /// 本股在板块里的位置：一句结论 + 分布条。
    @ViewBuilder
    private var positionBlock: some View {
        if metric.positionText != nil || metric.distribution != nil || metric.statusNote != nil {
            VStack(alignment: .leading, spacing: 10) {
                Text(research.peerGroup.map { L("在%@板块 %lld 家公司中的位置", $0.sectorName, $0.sampleSize) }
                     ?? L("在板块中的位置"))
                    .font(QuantTypography.metadata.weight(.semibold)).foregroundStyle(Theme.textSecondary)
                if let pos = metric.positionText {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text(pos).font(QuantTypography.emphasis).foregroundStyle(Theme.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                        QuantInfoMark()
                    }
                    .quantExplain(L("百分位和等级怎么来的")) {
                        QuantMetricGradeExplanation(metric: metric, peer: research.peerGroup)
                    }
                }
                if let note = metric.statusNote {
                    Text(note).font(QuantTypography.body).foregroundStyle(Theme.segment)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let dist = metric.distribution {
                    VStack(alignment: .leading, spacing: 2) {
                        DistributionStrip(distribution: dist, value: metric.value, valueLabel: metric.displayValue,
                                          symbol: research.symbol, lowerBetter: metric.lowerBetter,
                                          isPercent: metric.displayValue.hasSuffix("%"))
                        HStack(spacing: 4) {
                            Text(L("P10、P25、P90 是什么？")).font(QuantTypography.metadata).foregroundStyle(Theme.accent)
                            QuantInfoMark()
                        }
                    }
                    .padding(.top, 4)
                    .quantExplain(L("这条分布线怎么看")) {
                        QuantDistributionExplanation(metric: metric, research: research)
                    }
                }
            }
            .padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
        }
    }

    /// 高低怎么看 + 需要注意的边界。
    private var readingBlock: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(L("怎么看"), systemImage: metric.lowerBetter ? "arrow.down.circle" : "arrow.up.circle")
                .font(QuantTypography.metadata.weight(.semibold)).foregroundStyle(Theme.textSecondary)
            Text(itp?.reading.flatMap { $0.isEmpty ? nil : $0 }
                 ?? (metric.lowerBetter ? L("越低排名越靠前") : L("越高排名越靠前")))
                .font(QuantTypography.body).foregroundStyle(Theme.textPrimary)
                .lineSpacing(3).fixedSize(horizontal: false, vertical: true)
            if let role = itp?.role, !role.isEmpty, plain == nil {
                Text(role).font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                    .lineSpacing(3).fixedSize(horizontal: false, vertical: true)
            }
            if let threshold = itp?.threshold, !threshold.isEmpty {
                Divider().overlay(Theme.border)
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill").font(QuantTypography.metadata)
                        .foregroundStyle(Theme.segment).padding(.top, 2)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(L("需要注意")).font(QuantTypography.metadata.weight(.semibold))
                            .foregroundStyle(Theme.textSecondary)
                        Text(threshold).font(QuantTypography.body).foregroundStyle(Theme.textPrimary.opacity(0.85))
                            .lineSpacing(2).fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
        .padding(14).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
    }

    /// 怎么算：口径定义 + 代入本股数据 + 等级分档，默认折叠。
    private var calculationGroup: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 10) {
                if plain != nil, let what = itp?.what, !what.isEmpty {
                    Text(what).font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let f = metric.formula {
                    calcCard(f)
                } else {
                    box(title: nil) {
                        Text(itp?.calculation ?? metric.description)
                            .font(QuantTypography.body).foregroundStyle(Theme.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(L("当前数据不足，暂无可代入的计算结果。"))
                            .font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                    }
                }
                if metric.positionText != nil {
                    Text(L("等级 = 板块百分位分档：≥93 A+ · ≥86 A · ≥80 A- · … · <20 F"))
                        .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 10)
        } label: {
            Label(L("怎么算"), systemImage: "function")
        }
        .font(QuantTypography.body).foregroundStyle(Theme.textPrimary).tint(Theme.accent)
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
    }

    private func calcCard(_ f: QuantFormula) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let calculation = metric.interpretation?.calculation {
                Text(L("公式")).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
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
                            if let hint = i.hint {
                                HStack(spacing: 3) {
                                    Text(i.label).foregroundStyle(Theme.textSecondary)
                                    QuantInfoMark()
                                }
                                .quantExplain(i.label) { QuantExplainText(text: hint) }
                            } else {
                                Text(i.label).foregroundStyle(Theme.textSecondary)
                            }
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
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
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
