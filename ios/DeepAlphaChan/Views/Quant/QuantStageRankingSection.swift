import SwiftUI

/// 点企业阶段时展示：该阶段综合分前 30 家，并标出本股排在第几。
/// 只陈列本模型的综合分（同阶段公司在一起比），不是推荐榜；本股不在前 30 时在末尾单独列出位置。
/// 点别的公司打开它的分析（`StockAnalysisCover`，独立状态、走同样的免费额度）。
struct QuantStageRankingSection: View {
    let selected: QuantLifecycleStage
    let research: QuantResearch

    @State private var ranking: QuantStageRanking?
    @State private var failed = false
    @State private var opening: StockAnalysisCover.Target?

    /// 本股属于这个阶段时才传本股信息（别的阶段只看排名，不算本股位置）
    private var isCurrent: Bool { research.stage?.key == selected.rawValue }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(L("%@综合分排名", selected.title))
                .font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
            if let r = ranking {
                content(r)
            } else if failed {
                Text(L("排名暂时加载不出来，稍后再试。"))
                    .font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
            } else {
                ProgressView().frame(maxWidth: .infinity, alignment: .center).padding(.vertical, 8)
            }
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16))
        .task(id: selected) { await load() }
        .fullScreenCover(item: $opening) { target in
            StockAnalysisCover(target: target)
        }
    }

    @ViewBuilder
    private func content(_ r: QuantStageRanking) -> some View {
        if r.cohortSize == 0 {
            Text(L("这个阶段暂时没有样本公司。"))
                .font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
        } else {
            if let me = r.selfItem {
                Text(me.inUniverse
                     ? L("%@ 在 %lld 家%@公司里排第 %lld。", research.symbol, me.total, selected.title, me.rank)
                     : L("%@ 不在样本内，按它的综合分估算，在 %lld 家%@公司里约排第 %lld。", research.symbol, me.total, selected.title, me.rank))
                    .font(QuantTypography.emphasis).foregroundStyle(Theme.accent)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text(L("共 %lld 家%@公司，按综合分从高到低。", r.cohortSize, selected.title))
                    .font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
            }
            VStack(spacing: 0) {
                ForEach(r.items) { item in
                    row(rank: item.rank, symbol: item.symbol, name: item.name, grade: item.grade,
                        score: item.score, highlight: item.isSelf)
                }
                if let me = r.selfItem, !r.items.contains(where: \.isSelf) {
                    Text("⋯").font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                        .frame(maxWidth: .infinity).padding(.vertical, 2)
                    row(rank: me.rank, symbol: research.symbol, name: research.name, grade: research.overall?.grade,
                        score: research.overall?.score, highlight: true, approximate: !me.inUniverse)
                }
            }
            Text(L("排名只是本模型综合分的高低：同阶段公司在一起比，综合分包含估值、动量等会随股价变化的维度。不代表公司好坏的定论，也不构成投资建议。"))
                .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let d = r.asOf {
                Text(L("数据日期：%@", d)).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
            }
        }
    }

    @ViewBuilder
    private func row(rank: Int, symbol: String, name: String?, grade: String?, score: Double?,
                     highlight: Bool, approximate: Bool = false) -> some View {
        if symbol.uppercased() == research.symbol.uppercased() {
            rowContent(rank: rank, symbol: symbol, name: name, grade: grade, score: score,
                       highlight: highlight, approximate: approximate, tappable: false)
        } else {
            Button {
                if let market = StockMarket(rawValue: research.market) {
                    opening = .init(market: market, symbol: symbol, name: name)
                }
            } label: {
                rowContent(rank: rank, symbol: symbol, name: name, grade: grade, score: score,
                           highlight: highlight, approximate: approximate, tappable: true)
            }
            .buttonStyle(.plain)
            .accessibilityHint(L("打开这只股票的分析"))
        }
    }

    private func rowContent(rank: Int, symbol: String, name: String?, grade: String?, score: Double?,
                            highlight: Bool, approximate: Bool, tappable: Bool) -> some View {
        HStack(spacing: 10) {
            Text(approximate ? "≈\(rank)" : "\(rank)")
                .font(QuantTypography.body.monospacedDigit())
                .foregroundStyle(Theme.textSecondary)
                .frame(minWidth: 34, alignment: .leading)
            VStack(alignment: .leading, spacing: 1) {
                Text(symbol).font(QuantTypography.emphasis).foregroundStyle(Theme.textPrimary)
                if let name, !name.isEmpty {
                    Text(name).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary).lineLimit(1)
                }
            }
            Spacer(minLength: 8)
            if let score {
                Text(String(format: "%.1f", score))
                    .font(QuantTypography.body.monospacedDigit()).foregroundStyle(Theme.textSecondary)
            }
            QuantGradeBlock(grade: grade, side: 30)
            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.textSecondary)
                .opacity(tappable ? 1 : 0)
        }
        .padding(.vertical, 6).padding(.horizontal, 6)
        .frame(minHeight: 44)
        .contentShape(Rectangle())
        .background(highlight ? Theme.accent.opacity(0.12) : Color.clear, in: RoundedRectangle(cornerRadius: 8))
    }

    private func load() async {
        failed = false
        let symbol = isCurrent ? research.symbol : nil
        let score = isCurrent ? research.overall?.score : nil
        if let hit = await QuantResearchService.cachedStageRanking(market: research.market, stage: selected.rawValue,
                                                                    symbol: symbol, score: score) {
            ranking = hit
            return
        }
        ranking = nil
        do {
            ranking = try await QuantResearchService.stageRanking(
                market: research.market, stage: selected.rawValue, symbol: symbol, score: score)
        } catch {
            failed = true
        }
    }
}
