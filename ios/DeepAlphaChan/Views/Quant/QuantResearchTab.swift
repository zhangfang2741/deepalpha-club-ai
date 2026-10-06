import SwiftUI

/// 量化研究首页：先读摘要，再看判断依据，最后按需展开图表与数据方法。
struct QuantResearchTab: View {
    let market: StockMarket
    let symbol: String
    @ObservedObject var vm: QuantResearchViewModel
    var isStatic = false
    @State private var latestReport: LatestReport?


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
                    QuantMessageCard(text: r.statusNote ?? L("暂无基本面研究数据"), footnote: r.disclaimer)
                }
            }
        }
        .task { await vm.loadResearch(market: market, symbol: symbol) }
        // 最新财报单独加载：失败或没有就不显示这张卡，不影响其他内容
        .task(id: symbol) {
            guard !isStatic else { return }
            let r = try? await QuantResearchService.latestReport(market: market, symbol: symbol)
            withAnimation(.easeOut(duration: 0.2)) { latestReport = r }
        }
    }

    @ViewBuilder
    private func content(_ r: QuantResearch) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            QuantResearchSummaryCard(research: r, isStatic: isStatic)
            if !isStatic, let report = latestReport, report.isOK {
                LatestReportCard(market: market, symbol: symbol, report: report).transition(.opacity)
            }
            if QuantMoatCard.isEnabled, let moat = r.moat {
                QuantMoatCard(moat: moat, isStatic: isStatic)
            }
            VStack(alignment: .leading, spacing: 8) {
                Text(L("五维成绩单")).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                    .padding(.horizontal, 4)
                VStack(alignment: .leading, spacing: 0) {
                    groupCaption(L("生意与价格"))
                    dimensionRows(r, keys: ["profitability", "growth", "valuation"])
                    groupCaption(L("市场与预期"))
                    dimensionRows(r, keys: ["momentum", "revisions"])
                }
                .padding(.horizontal, 14).padding(.bottom, 4)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16))
                Text(isStatic ? QuantDimensionGuide.gradeReading
                     : QuantDimensionGuide.gradeReading + L("点任意等级可查看评分标准。"))
                    .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
            }
            QuantStageTimeline(research: r, isStatic: isStatic)
            if !isStatic {
                VStack(spacing: 0) {
                    DisclosureGroup {
                        VStack(alignment: .leading, spacing: 12) {
                            if let asOf = r.asOf {
                                Text(asOfText(asOf)).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                            }
                            NavigationLink {
                                QuantMethodologyView(vm: vm)
                            } label: {
                                Label(L("等级是怎么算的？"), systemImage: "arrow.up.right")
                                    .frame(minHeight: 44)
                            }
                        }
                    } label: {
                        Label(L("数据与方法"), systemImage: "doc.text.magnifyingglass")
                            .frame(minHeight: 44)
                    }
                }
                 .font(QuantTypography.body).foregroundStyle(Theme.textPrimary).tint(Theme.accent)
                .padding(.horizontal, 16).padding(.vertical, 4)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16))
            } else if let asOf = r.asOf {
                Text(asOfText(asOf)).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
            }
            Text(r.disclaimer).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func groupCaption(_ text: String) -> some View {
        Text(text).font(QuantTypography.metadata.weight(.semibold))
            .foregroundStyle(Theme.textSecondary).padding(.top, 12)
    }

    @ViewBuilder
    private func dimensionRows(_ research: QuantResearch, keys: [String]) -> some View {
        ForEach(Array(keys.enumerated()), id: \.element) { index, key in
            if index > 0 { Divider().overlay(Theme.border).padding(.leading, 56) }
            if let dimension = research.dimensions.first(where: { $0.key == key }) {
                if isStatic {
                    QuantDimensionRow(dimension: dimension, isStatic: true)
                } else {
                    NavigationLink {
                        QuantDimensionDetailView(dimension: dimension, research: research)
                    } label: {
                        QuantDimensionRow(dimension: dimension)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func asOfText(_ a: QuantAsOf) -> String {
        var parts: [String] = []
        if let d = a.priceDate { parts.append(L("行情 %@ 收盘", d)) }
        if let p = a.fiscalPeriod {
            parts.append(a.filingDate.map { L("财报 %@（%@ 披露）", p, $0) } ?? L("财报 %@", p))
        }
        if let e = a.estimatesDate { parts.append(L("预期 %@ 更新", e)) }
        let line = parts.joined(separator: " · ")
        // 港股：财务数据与预期折成港元的汇率说明（后端按语言生成），另起一行
        guard let note = a.currencyNote else { return line }
        return line.isEmpty ? note : "\(line)\n\(note)"
    }
}

/// 0~100 的百分位条，灰色竖线标板块中位（50）。
struct QuantPercentileBar: View {
    let percentile: Double
    let color: Color

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.surfaceAlt).frame(height: 3)
                Capsule().fill(color.opacity(0.8))
                    .frame(width: geo.size.width * CGFloat(min(max(percentile, 0), 100) / 100), height: 3)
                Rectangle().fill(Theme.textSecondary).frame(width: 1, height: 7)
                    .offset(x: geo.size.width / 2 - 0.5)
            }
            .frame(height: 7)
        }
        .frame(height: 7)
    }
}

struct QuantSectionHeader: View {
    let text: String
    var trailing: String?

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(text).font(QuantTypography.title)
            Spacer()
            if let trailing { Text(trailing).font(QuantTypography.metadata).multilineTextAlignment(.trailing) }
        }
        .foregroundStyle(Theme.textSecondary)
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
            Text(text).font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
            if let retry {
                Button(L("重试"), action: retry).font(QuantTypography.emphasis).tint(Theme.accent)
            }
            if let footnote {
                Text(footnote).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
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
