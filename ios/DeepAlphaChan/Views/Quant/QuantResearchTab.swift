import SwiftUI

/// 详情页「量化研究」分段首页：综合等级窄卡 → 五张维度卡片（固定顺序，最高 / 最低加高亮边框）
/// → 五维图总览 → 方法说明入口 → 免责。所有文案来自后端（按 App 语言生成）。
struct QuantResearchTab: View {
    let market: StockMarket
    let symbol: String
    @ObservedObject var vm: QuantResearchViewModel
    var isStatic = false

    @State private var showStage = false

    var body: some View {
        Group {
            switch vm.research {
            case .idle, .loading:
                ProgressView().tint(Theme.accent).frame(maxWidth: .infinity, minHeight: 220)
            case .failed(let message):
                QuantMessageCard(text: message, retry: {
                    Task { await vm.loadResearch(market: market, symbol: symbol, force: true) }
                })
            case .loaded(let r):
                if r.isOK {
                    content(r)
                } else {
                    QuantMessageCard(text: r.statusNote ?? L("暂无量化研究数据"), footnote: r.disclaimer)
                }
            }
        }
        .task { await vm.loadResearch(market: market, symbol: symbol) }
    }

    @ViewBuilder
    private func content(_ r: QuantResearch) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            overallCard(r)
            QuantSectionHeader(text: L("五个维度"), trailing: r.peerGroup?.text)
            ForEach(r.dimensions) { d in
                if isStatic {
                    QuantDimensionCard(dimension: d)
                } else {
                    NavigationLink {
                        QuantDimensionDetailView(dimension: d, research: r)
                    } label: {
                        QuantDimensionCard(dimension: d)
                    }
                    .buttonStyle(.plain)
                }
            }
            QuantSectionHeader(text: L("五维总览"))
            FiveDimensionChart(dimensions: r.dimensions, symbol: r.symbol)
                .padding(.horizontal, 8)
                .padding(.vertical, 12)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
            if !isStatic {
                NavigationLink {
                    QuantMethodologyView(vm: vm)
                } label: {
                    HStack {
                        Text(L("等级是怎么算的？"))
                        Spacer()
                        Image(systemName: "chevron.right").font(.caption.weight(.semibold))
                    }
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Theme.accent)
                    .padding(14)
                    .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
                }
                .buttonStyle(.plain)
            }
            Text(r.disclaimer)
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)
                .padding(.top, 4)
        }
    }

    private func overallCard(_ r: QuantResearch) -> some View {
        let o = r.overall
        return VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(L("综合等级")).font(.footnote).foregroundStyle(Theme.textSecondary)
                Text(o?.grade ?? "—")
                    .font(.system(size: 30, weight: .heavy))
                    .foregroundStyle(QuantGradeStyle.color(o?.grade))
                if let text = o?.text {
                    Text(text).font(.subheadline).foregroundStyle(Theme.textPrimary)
                        .lineLimit(2).minimumScaleFactor(0.85)
                }
                Spacer(minLength: 0)
            }
            if let note = o?.note {
                Text(note).font(.footnote).foregroundStyle(Theme.segment)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let stage = r.stage {
                Button { withAnimation(.easeInOut(duration: 0.2)) { showStage.toggle() } } label: {
                    HStack(spacing: 6) {
                        Text(stage.unprofitable ? L("%@ · 尚未盈利", stage.name) : stage.name)
                            .font(.caption.weight(.semibold))
                            .padding(.horizontal, 8).padding(.vertical, 3)
                            .background(Theme.surfaceAlt, in: Capsule())
                        Image(systemName: showStage ? "chevron.up" : "info.circle")
                            .font(.caption2)
                        Spacer()
                    }
                    .foregroundStyle(Theme.textSecondary)
                }
                .buttonStyle(.plain)
                .disabled(isStatic)
                if showStage && !isStatic {
                    stageDetail(stage)
                }
            }
            if let asOf = r.asOf {
                Text(asOfText(asOf)).font(.caption2).foregroundStyle(Theme.textSecondary)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16)
            .stroke(QuantGradeStyle.color(o?.grade).opacity(0.45), lineWidth: 1.5))
    }

    private func stageDetail(_ stage: QuantStage) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(stage.note).font(.footnote).foregroundStyle(Theme.textPrimary.opacity(0.9))
                .fixedSize(horizontal: false, vertical: true)
            ForEach([(L("经营现金流"), stage.cashFlows.operating),
                     (L("投资现金流"), stage.cashFlows.investing),
                     (L("筹资现金流"), stage.cashFlows.financing)], id: \.0) { name, value in
                HStack {
                    Text(name).foregroundStyle(Theme.textSecondary)
                    Spacer()
                    Text(QuantFormat.money(value)).monospacedDigit()
                        .foregroundStyle(value >= 0 ? Theme.textPrimary : Theme.down)
                }
                .font(.caption)
            }
            Text(L("按最近 12 个月三项现金流的正负划分阶段，只做标注，不影响等级。"))
                .font(.caption2).foregroundStyle(Theme.textSecondary)
        }
        .padding(10)
        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
    }

    private func asOfText(_ a: QuantAsOf) -> String {
        var parts: [String] = []
        if let d = a.priceDate { parts.append(L("行情 %@ 收盘", d)) }
        if let p = a.fiscalPeriod {
            parts.append(a.filingDate.map { L("财报 %@（%@ 披露）", p, $0) } ?? L("财报 %@", p))
        }
        if let e = a.estimatesDate { parts.append(L("预期 %@ 更新", e)) }
        return parts.joined(separator: " · ")
    }
}

/// 一张维度卡片：等级、名称、关键事实、板块百分位条（灰线 = 板块中位）。
struct QuantDimensionCard: View {
    let dimension: QuantDimension

    var body: some View {
        let d = dimension
        let highlight = d.isHighest || d.isLowest
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 10) {
                QuantGradeBadge(grade: d.grade)
                Text(d.name).font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.textPrimary)
                if d.isHighest { tag(L("最高")) }
                if d.isLowest { tag(L("最低")) }
                Spacer()
                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(Theme.textSecondary)
            }
            Text(d.keyFact?.text ?? d.statusNote ?? d.description)
                .font(.subheadline)
                .foregroundStyle(d.isOK ? Theme.textPrimary : Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let score = d.score {
                QuantPercentileBar(percentile: score, color: QuantGradeStyle.color(d.grade))
                HStack {
                    Text(L("维度分 %@", String(format: "%.1f", score)))
                    Spacer()
                    Text(L("查看 %@ 的指标", d.name)).foregroundStyle(Theme.accent)
                }
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14)
            .stroke(highlight ? QuantGradeStyle.color(d.grade).opacity(0.6) : .clear, lineWidth: 1.5))
        .contentShape(Rectangle())
    }

    private func tag(_ text: String) -> some View {
        Text(text).font(.caption2)
            .padding(.horizontal, 5).padding(.vertical, 1)
            .overlay(RoundedRectangle(cornerRadius: 5).stroke(Theme.border))
            .foregroundStyle(Theme.textSecondary)
    }
}

/// 0~100 的百分位条，灰色竖线标板块中位（50）。
struct QuantPercentileBar: View {
    let percentile: Double
    let color: Color

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.surfaceAlt)
                Capsule().fill(color).frame(width: geo.size.width * CGFloat(min(max(percentile, 0), 100) / 100))
                Rectangle().fill(Theme.textSecondary).frame(width: 1.5, height: 11)
                    .offset(x: geo.size.width / 2 - 0.75)
            }
        }
        .frame(height: 5)
        .padding(.vertical, 3)
    }
}

struct QuantSectionHeader: View {
    let text: String
    var trailing: String?

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(text).font(.system(size: 13, weight: .semibold))
            Spacer()
            if let trailing { Text(trailing).font(.caption2).multilineTextAlignment(.trailing) }
        }
        .foregroundColor(Theme.textSecondary)
        .padding(.horizontal, 4)
        .padding(.top, 6)
    }
}

/// 状态 / 错误卡片（不支持的市场、数据不足、网络失败）。
struct QuantMessageCard: View {
    let text: String
    var footnote: String?
    var retry: (() -> Void)?

    var body: some View {
        VStack(spacing: 10) {
            Text(text).font(.subheadline).foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
            if let retry {
                Button(L("重试"), action: retry).font(.footnote.weight(.semibold)).tint(Theme.accent)
            }
            if let footnote {
                Text(footnote).font(.caption2).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, minHeight: 160)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
    }
}

enum QuantFormat {
    /// 金额缩写（与后端 fmt_money 一致）。
    static func money(_ v: Double) -> String {
        let a = abs(v)
        if Localized.language() == .english {
            if a >= 1e12 { return String(format: "%.2fT", v / 1e12) }
            if a >= 1e9 { return String(format: "%.1fB", v / 1e9) }
            return String(format: "%.1fM", v / 1e6)
        }
        if a >= 1e12 { return String(format: "%.2f 万亿", v / 1e12) }
        if a >= 1e8 { return String(format: "%.1f 亿", v / 1e8) }
        return String(format: "%.1f 万", v / 1e4)
    }
}
