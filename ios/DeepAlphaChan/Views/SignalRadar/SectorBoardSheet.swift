import SwiftUI

/// 行业弹层：各行业按相对大盘强弱从强到弱，每行带状态色点、强弱、宽基雷达当日的买卖点数。
/// 点一级行业 → 关闭弹层，雷达切到宽基并只显示该行业的气泡；有子行业的可下钻看细分（只展示）。
struct SectorBoardSheet: View {
    let market: StockMarket
    let onPick: (_ key: String, _ name: String, _ universe: String) -> Void

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            SectorBoardList(market: market, parent: nil, parentName: nil) { key, name, universe in
                onPick(key, name, universe)
                dismiss()
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) { Button(L("关闭")) { dismiss() } }
            }
        }
    }
}

private struct SectorBoardList: View {
    let market: StockMarket
    let parent: String?
    let parentName: String?
    let onPick: (_ key: String, _ name: String, _ universe: String) -> Void

    @State private var board: SectorBoard?
    @State private var failed = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let board, !board.sectors.isEmpty {
                    header(board)
                    VStack(spacing: 0) {
                        ForEach(board.sectors) { row in
                            rowView(row, board: board)
                            if row.id != board.sectors.last?.id { Divider().overlay(Theme.border) }
                        }
                    }
                    .background(Theme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    Text(L("以上内容为对市场环境的客观描述，不构成任何投资建议。"))
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                } else if failed || board != nil {
                    VStack(spacing: 10) {
                        Text(board == nil ? L("加载失败，请稍后再试") : L("数据准备中"))
                            .font(.footnote).foregroundColor(Theme.textSecondary)
                        Button(L("重试")) { Task { await load() } }
                            .buttonStyle(.bordered).tint(Theme.accent)
                    }
                    .frame(maxWidth: .infinity).padding(.top, 60)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 60)
                }
            }
            .padding(16)
        }
        .background(Theme.background)
        .navigationTitle(parentName ?? L("%@行业", market.title))
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        failed = false
        do {
            board = try await MarketOverviewService.sectors(market: market, parent: parent)
        } catch {
            failed = true
        }
    }

    private func header(_ board: SectorBoard) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(L("按近 20 个交易日相对大盘的强弱排序，颜色为行业状态（红=逐利、灰=观望、绿=避险）。"))
            if parent == nil, let name = board.radarUniverseName {
                if let date = board.radarDate {
                    Text(L("买卖点为%@成分股 %@ 的雷达统计；点行业只看该行业的气泡。", L(name), date))
                } else {
                    Text(L("点行业只看该行业在%@里的气泡。", L(name)))
                }
            }
            if let asOf = board.asOf { Text(L("%@ 收盘数据", asOf)) }
        }
        .font(.caption2)
        .foregroundColor(Theme.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private func rowView(_ row: SectorRow, board: SectorBoard) -> some View {
        let content = HStack(spacing: 10) {
            Circle().fill(MarketHeader.regimeColor(row.label)).frame(width: 8, height: 8)
            Text(row.name).font(.subheadline.weight(.medium)).foregroundColor(Theme.textPrimary)
            Spacer(minLength: 6)
            if parent == nil, row.buyCount + row.sellCount > 0 {
                HStack(spacing: 4) {
                    Text(L("%lld 买", row.buyCount)).foregroundColor(Theme.up)
                    Text(L("%lld 卖", row.sellCount)).foregroundColor(Theme.down)
                }
                .font(.caption.monospacedDigit())
            }
            Text(SectorBoardList.rsText(row.rsVsMarket))
                .font(.caption.monospacedDigit())
                .foregroundColor((row.rsVsMarket ?? 0) >= 0 ? Theme.up : Theme.down)
                .frame(width: 56, alignment: .trailing)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .contentShape(Rectangle())

        if parent == nil {
            HStack(spacing: 0) {
                Button {
                    onPick(row.key, row.name, board.radarUniverse ?? "")
                } label: { content }
                .buttonStyle(.plain)
                .disabled(board.radarUniverse == nil)
                if row.hasChildren {
                    NavigationLink {
                        SectorBoardList(market: market, parent: row.key, parentName: row.name, onPick: onPick)
                    } label: {
                        Image(systemName: "list.bullet.indent")
                            .font(.system(size: 13))
                            .foregroundColor(Theme.textSecondary)
                            .padding(.trailing, 14)
                            .padding(.vertical, 12)
                    }
                    .accessibilityLabel(L("查看细分行业"))
                }
            }
        } else {
            content
        }
    }

    /// 0.032 → 「+3.2%」。
    static func rsText(_ rs: Double?) -> String {
        guard let rs else { return "--" }
        return String(format: "%+.1f%%", rs * 100)
    }
}
