import SwiftUI

/// 弹层里展示的雷达统计：当前雷达所看的指数、日期与按行业的买卖点数（与雷达上方的行业筛选条同一份）。
struct SectorRadarContext {
    let universeName: String
    let date: String
    let counts: [String: [String: Int]]
    let selectedKey: String?
}

/// 行业弹层：各行业按相对大盘强弱从强到弱，每行带状态色点、强弱、当前雷达选中日的买卖点数。
/// 点一级行业 → 关闭弹层，雷达在当前指数里只看该行业（等同于在筛选条上选中它，不切换指数）；
/// 有子行业的可下钻看细分（只展示）。radar 为 nil（自选等没有行业统计的雷达）时行业只展示、不可筛。
struct SectorBoardSheet: View {
    let market: StockMarket
    let radar: SectorRadarContext?
    let onPick: (_ key: String, _ name: String) -> Void

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            SectorBoardList(market: market, parent: nil, parentName: nil, radar: radar) { key, name in
                onPick(key, name)
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
    let radar: SectorRadarContext?
    let onPick: (_ key: String, _ name: String) -> Void

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
            if parent == nil, let radar {
                Text(L("买卖点为%@ %@ 的雷达统计；点行业即在雷达上只看该行业。", radar.universeName, radar.date))
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
            if parent == nil, radar?.selectedKey == row.key {
                Image(systemName: "checkmark").font(.caption.weight(.bold)).foregroundColor(Theme.accent)
            }
            Spacer(minLength: 6)
            if parent == nil, let c = radar?.counts[row.key], (c["buy"] ?? 0) + (c["sell"] ?? 0) > 0 {
                HStack(spacing: 4) {
                    Text(L("%lld 买", c["buy"] ?? 0)).foregroundColor(Theme.up)
                    Text(L("%lld 卖", c["sell"] ?? 0)).foregroundColor(Theme.down)
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
                    onPick(row.key, row.name)
                } label: { content }
                .buttonStyle(.plain)
                .disabled(radar == nil)
                if row.hasChildren {
                    NavigationLink {
                        SectorBoardList(market: market, parent: row.key, parentName: row.name, radar: radar, onPick: onPick)
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
