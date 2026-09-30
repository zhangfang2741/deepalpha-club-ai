import SwiftUI

/// 指标详情（半屏 sheet）：定义 → 带真实数字的算式 → 本股在板块分布中的位置（P10 ~ P90）
/// → 「位置 → 百分位 → 等级」推导 → 原始数据与各自的时间点。让每个等级都能追到原始数据。
struct QuantMetricSheet: View {
    let metric: QuantMetric
    let research: QuantResearch

    var body: some View {
        ScrollView {
            QuantMetricDetailContent(metric: metric, research: research)
        }
        .background(Theme.surface)
    }
}

/// 指标详情的内容本体（不含滚动容器，便于离屏渲染验收）。
struct QuantMetricDetailContent: View {
    let metric: QuantMetric
    let research: QuantResearch

    var body: some View {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text(metric.name).font(.system(size: 18, weight: .bold)).foregroundStyle(Theme.textPrimary)
                    Spacer()
                    QuantGradeBadge(grade: metric.grade, size: 16)
                }
                Text(metric.description).font(.footnote).foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(metric.lowerBetter ? L("越低在板块中排名越靠前") : L("越高在板块中排名越靠前"))
                    .font(.caption2).foregroundStyle(Theme.textSecondary)

                if let f = metric.formula {
                    box(title: L("计算")) {
                        Text(f.expression)
                            .font(.system(size: 15, weight: .semibold).monospacedDigit())
                            .foregroundStyle(Theme.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                if let note = metric.statusNote {
                    Text(note).font(.footnote).foregroundStyle(Theme.segment)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let dist = metric.distribution, let peer = research.peerGroup {
                    Text(L("在%@板块 %lld 家公司中的位置", peer.sectorName, peer.sampleSize))
                        .font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.textSecondary)
                    DistributionStrip(distribution: dist, value: metric.value, valueLabel: metric.displayValue,
                                      symbol: research.symbol, lowerBetter: metric.lowerBetter,
                                      isPercent: metric.displayValue.hasSuffix("%"))
                }
                if let pos = metric.positionText {
                    box(title: nil) {
                        Text(pos).font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(L("分档：≥93 A+ · ≥86 A · ≥80 A- · … · <20 F"))
                            .font(.caption2).foregroundStyle(Theme.textSecondary)
                    }
                }
                if let inputs = metric.formula?.inputs, !inputs.isEmpty {
                    Text(L("原始数据")).font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.textSecondary)
                    VStack(spacing: 0) {
                        ForEach(inputs) { i in
                            HStack(alignment: .firstTextBaseline) {
                                Text(i.label).foregroundStyle(Theme.textSecondary)
                                Spacer(minLength: 12)
                                VStack(alignment: .trailing, spacing: 2) {
                                    Text(i.value).monospacedDigit().foregroundStyle(Theme.textPrimary)
                                    if let note = i.note {
                                        Text(note).font(.caption2).foregroundStyle(Theme.textSecondary)
                                            .multilineTextAlignment(.trailing)
                                    }
                                }
                            }
                            .font(.footnote)
                            .padding(.vertical, 7)
                            Divider().background(Theme.border)
                        }
                        if let peer = research.peerGroup {
                            HStack {
                                Text(L("板块样本")).foregroundStyle(Theme.textSecondary)
                                Spacer()
                                Text(L("%lld 家", peer.sampleSize)).foregroundStyle(Theme.textPrimary)
                            }
                            .font(.footnote).padding(.vertical, 7)
                        }
                    }
                }
            }
            .padding(18)
    }

    private func box<C: View>(title: String?, @ViewBuilder _ content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if let title { Text(title).font(.caption).foregroundStyle(Theme.textSecondary) }
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
                    .frame(height: 8).clipShape(Capsule()).offset(y: 22)
                ForEach(ticks, id: \.0) { name, v in
                    VStack(spacing: 1) {
                        Text(Self.short(v, isPercent: isPercent)).font(.system(size: 10).monospacedDigit())
                        Text(name).font(.system(size: 9))
                    }
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize()
                    .position(x: x(v), y: 48)
                }
                if let value {
                    let px = min(max(x(value), 2), w - 2)
                    Rectangle().fill(Theme.textPrimary).frame(width: 3, height: 22)
                        .position(x: px, y: 26)
                    Text("\(symbol) \(valueLabel)")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(Theme.textPrimary)
                        .fixedSize()
                        .position(x: min(max(px, 40), w - 40), y: 6)
                }
            }
        }
        .frame(height: 62)
    }

    static func short(_ v: Double, isPercent: Bool) -> String {
        if isPercent { return String(format: "%.0f%%", v * 100) }
        let a = abs(v)
        if a >= 100 { return String(format: "%.0f", v) }
        if a >= 10 { return String(format: "%.1f", v) }
        return String(format: "%.2f", v)
    }
}
