import SwiftUI

/// 弹层里展示的雷达统计：当前雷达所看的指数、日期与按行业的买卖点数（与雷达上方的行业筛选条同一份）。
struct SectorRadarContext {
    let universeName: String
    let date: String
    let counts: [String: [String: Int]]
    let selectedKey: String?
    /// 当天全部买卖点数（含没有行业标签的），给「全部行业」一行用；nil 时按各行业相加。
    var totals: (buy: Int, sell: Int)?
}

/// 行业弹层：各行业按相对大盘强弱从强到弱，每行带状态色点、强弱、当前雷达选中日的买卖点数。
/// 行业严格按 GICS 一级行业，只有一级、不下钻。点行业 → 关闭弹层，雷达在当前指数里只看该行业
/// （等同于在筛选条上选中它，不切换指数）。radar 为 nil（自选等没有行业统计的雷达）时行业只展示、不可筛。
struct SectorBoardSheet: View {
    let market: StockMarket
    /// 按该日收盘取强弱（雷达所选日，与筛选条排序一致）；nil 取最新。
    let date: String?
    let radar: SectorRadarContext?
    let onPick: (_ key: String, _ name: String) -> Void
    /// 选「全部行业」（取消筛选）；nil 时不显示这一行。
    var onClear: (() -> Void)?

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            SectorBoardList(market: market, date: date, parent: nil, parentName: nil, radar: radar,
                            onPick: { key, name in
                                onPick(key, name)
                                dismiss()
                            },
                            onClear: onClear.map { clear in { clear(); dismiss() } })
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) { Button(L("关闭")) { dismiss() } }
            }
        }
    }
}

/// 层级（从主到次）：分组（跑赢 / 跑输大盘）→ 行业名 + 强弱值与强弱条 → 状态与当日买卖点 → 说明文字。
/// 说明文字放到底部，顶部只留「哪天收盘」与状态图例，打开就先看到结论。
struct SectorBoardList: View {
    let market: StockMarket
    let date: String?
    let parent: String?
    let parentName: String?
    let radar: SectorRadarContext?
    let onPick: (_ key: String, _ name: String) -> Void
    let onClear: (() -> Void)?

    @State private var board: SectorBoard?
    @State private var failed = false

    /// 显式 init：有 private 的 @State，自动生成的成员初始化器只在本文件可见，雷达的行业面板要从别处推进来。
    init(market: StockMarket, date: String?, parent: String?, parentName: String?, radar: SectorRadarContext?,
         onPick: @escaping (_ key: String, _ name: String) -> Void, onClear: (() -> Void)? = nil) {
        self.market = market
        self.date = date
        self.parent = parent
        self.parentName = parentName
        self.radar = radar
        self.onPick = onPick
        self.onClear = onClear
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let board, !board.sectors.isEmpty {
                    summary(board)
                    if parent == nil, let radar, let onClear { allRow(radar, onClear: onClear) }
                    let maxAbs = max(board.sectors.compactMap { $0.rsVsMarket.map(abs) }.max() ?? 0, 0.0001)
                    let ahead = board.sectors.filter { ($0.rsVsMarket ?? -1) >= 0 }
                    let behind = board.sectors.filter { ($0.rsVsMarket ?? -1) < 0 }
                    if !ahead.isEmpty { section(L("跑赢大盘"), rows: ahead, maxAbs: maxAbs) }
                    if !behind.isEmpty { section(L("跑输大盘"), rows: behind, maxAbs: maxAbs) }
                    footer
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
            board = try await MarketOverviewService.sectors(market: market, parent: parent, date: date)
        } catch {
            failed = true
        }
    }

    // MARK: - 顶部 / 底部

    /// 顶部只留两件事：数据是哪天收盘的、圆点颜色是什么意思。
    private func summary(_ board: SectorBoard) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let asOf = board.asOf {
                Text(L("%@ 收盘 · 近 20 个交易日相对大盘", asOf))
                    .font(.footnote).foregroundColor(Theme.textSecondary)
            }
            HStack(spacing: 14) {
                legend("risk_on")
                legend("neutral")
                legend("risk_off")
            }
        }
    }

    private func legend(_ label: String) -> some View {
        HStack(spacing: 5) {
            Circle().fill(MarketHeader.regimeColor(label)).frame(width: 7, height: 7)
            Text(Self.labelText(label)).font(.caption).foregroundColor(Theme.textSecondary)
        }
    }

    /// 说明文字退到底部：怎么排的、点行业会怎样、免责。
    private var footer: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(L("按相对大盘的强弱排序；圆点为行业状态。"))
            if parent == nil, let radar {
                Text(L("买卖点为%@ %@ 的雷达统计；点行业即在雷达上只看该行业。", radar.universeName, radar.date))
            }
            Text(L("以上内容为对市场环境的客观描述，不构成任何投资建议。"))
        }
        .font(.caption2)
        .foregroundColor(Theme.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
    }

    /// 最上面一行「全部行业」：取消筛选，雷达回到全部信号。
    private func allRow(_ radar: SectorRadarContext, onClear: @escaping () -> Void) -> some View {
        let buys = radar.totals?.buy ?? radar.counts.values.reduce(0) { $0 + ($1["buy"] ?? 0) }
        let sells = radar.totals?.sell ?? radar.counts.values.reduce(0) { $0 + ($1["sell"] ?? 0) }
        let selected = radar.selectedKey == nil
        return Button(action: onClear) {
            HStack(spacing: 10) {
                Text(L("全部行业")).font(.body.weight(.semibold)).foregroundColor(Theme.textPrimary)
                if selected {
                    Image(systemName: "checkmark.circle.fill").font(.subheadline).foregroundColor(Theme.accent)
                }
                Spacer(minLength: 8)
                countChips(buy: buys, sell: sells)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(selected ? Theme.accent.opacity(0.12) : Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityHint(L("雷达显示全部行业的信号"))
    }

    /// 买卖点数：红买绿卖的小胶囊，没有就不画。
    @ViewBuilder
    private func countChips(buy: Int, sell: Int) -> some View {
        if buy + sell > 0 {
            HStack(spacing: 6) {
                if buy > 0 { chip(L("%lld 买", buy), color: Theme.up) }
                if sell > 0 { chip(L("%lld 卖", sell), color: Theme.down) }
            }
        }
    }

    private func chip(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.caption2.weight(.semibold).monospacedDigit())
            .foregroundColor(color)
            .padding(.horizontal, 7).padding(.vertical, 2)
            .background(color.opacity(0.14))
            .clipShape(Capsule())
    }

    // MARK: - 分组与行

    private func section(_ title: String, rows: [SectorRow], maxAbs: Double) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text(title).font(.subheadline.weight(.semibold)).foregroundColor(Theme.textPrimary)
                Text("\(rows.count)").font(.caption.monospacedDigit()).foregroundColor(Theme.textSecondary)
            }
            .padding(.horizontal, 4)
            VStack(spacing: 0) {
                ForEach(rows) { row in
                    rowView(row, maxAbs: maxAbs)
                    if row.id != rows.last?.id { Divider().overlay(Theme.border).padding(.leading, 14) }
                }
            }
            .background(Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14))
        }
    }

    /// 一行：左边行业名 + 状态胶囊，右边强弱值 + 强弱条，买卖点胶囊放在强弱条下方右对齐。
    private func rowView(_ row: SectorRow, maxAbs: Double) -> some View {
        let selected = parent == nil && radar?.selectedKey == row.key
        let rs = row.rsVsMarket
        let counts = parent == nil ? radar?.counts[row.key] : nil
        let content = HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Text(row.name).font(.body.weight(.semibold)).foregroundColor(Theme.textPrimary)
                    if selected {
                        Image(systemName: "checkmark.circle.fill").font(.subheadline).foregroundColor(Theme.accent)
                    }
                }
                HStack(spacing: 6) {
                    if let label = row.label {
                        chip(Self.labelText(label), color: MarketHeader.regimeColor(label))
                    }
                    countChips(buy: counts?["buy"] ?? 0, sell: counts?["sell"] ?? 0)
                }
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 6) {
                Text(SectorBoardList.rsText(rs))
                    .font(.title3.weight(.semibold).monospacedDigit())
                    .foregroundColor((rs ?? 0) >= 0 ? Theme.up : Theme.down)
                StrengthBar(value: rs ?? 0, maxAbs: maxAbs)
                    .frame(width: 96, height: 5)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .contentShape(Rectangle())
        .background(selected ? Theme.accent.opacity(0.12) : Color.clear)

        if parent == nil {
            Button {
                onPick(row.key, row.name)
            } label: { content }
            .buttonStyle(.plain)
            .disabled(radar == nil)
            .accessibilityHint(radar == nil ? "" : L("在雷达上只看该行业"))
        } else {
            content
        }
    }

    static func labelText(_ label: String) -> String {
        switch label {
        case "risk_on": return L("逐利")
        case "risk_off": return L("避险")
        default: return L("观望")
        }
    }

    /// 0.032 → 「+3.2%」。
    static func rsText(_ rs: Double?) -> String {
        guard let rs else { return "--" }
        return String(format: "%+.1f%%", rs * 100)
    }
}

/// 以 0 为中线的强弱条：跑赢向右（红）、跑输向左（绿），长度按本页最大绝对值归一，一眼看出差距。
private struct StrengthBar: View {
    let value: Double
    let maxAbs: Double

    var body: some View {
        GeometryReader { geo in
            let half = geo.size.width / 2
            let len = half * CGFloat(min(abs(value) / maxAbs, 1))
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.textSecondary.opacity(0.15))
                Capsule()
                    .fill(value >= 0 ? Theme.up : Theme.down)
                    .frame(width: max(len, 2))
                    .offset(x: value >= 0 ? half : half - len)
                Rectangle().fill(Theme.textSecondary.opacity(0.5)).frame(width: 1).offset(x: half)
            }
        }
        .accessibilityHidden(true)
    }
}
