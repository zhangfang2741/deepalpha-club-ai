import SwiftUI

/// 弹层里展示的雷达统计：当前雷达所看的指数、日期与按行业的买卖点数（与雷达上方的行业筛选条同一份）。
struct SectorRadarContext {
    let universeName: String
    let date: String
    let counts: [String: [String: Int]]
    let selectedKey: String?
    /// 当天全部买卖点数（含没有行业标签的），给「全部行业」一行用；nil 时按各行业相加。
    var totals: (buy: Int, sell: Int)?
    /// 基本面研究 / 分析师评级 tab：同一份 buy / sell 计数改按「升 / 降」类词显示（buy = 升、sell = 降）；
    /// nil = 缠论雷达的「买 / 卖」。note 是底部说明文字（带两个 %@：指数名、日期）。
    var eventWords: (up: String, down: String, note: String)?
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

    /// 点选后留 0.2 秒：先看到对勾与触感反馈、雷达在后面换好，再收起弹层，而不是点完瞬间消失。
    private func closeAfterFeedback() {
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(200))
            dismiss()
        }
    }

    var body: some View {
        NavigationStack {
            SectorBoardList(market: market, date: date, parent: nil, parentName: nil, radar: radar,
                            onPick: { key, name in
                                onPick(key, name)
                                closeAfterFeedback()
                            },
                            onClear: onClear.map { clear in { clear(); closeAfterFeedback() } })
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
            VStack(alignment: .leading, spacing: 10) {
                if let board, !board.sectors.isEmpty {
                    summary(board)
                    if parent == nil, let radar, let onClear { allRow(radar, onClear: onClear) }
                    let maxAbs = max(board.sectors.compactMap { $0.rsVsMarket.map(abs) }.max() ?? 0, 0.0001)
                    list(board.sectors, maxAbs: maxAbs)
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
                    skeleton
                }
            }
            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 16)
            .animation(.smooth(duration: 0.3), value: board?.asOf)
        }
        .scrollIndicators(.hidden)
        .background(Theme.background)
        .navigationTitle(parentName ?? L("%@行业", market.title))
        .navigationBarTitleDisplayMode(.inline)
        // 雷达换了选中日就重取；旧数据留在屏上直到新数据到，不闪空白。
        .task(id: date) { await load() }
    }

    private func load() async {
        failed = false
        do {
            let fresh = try await MarketOverviewService.sectors(market: market, parent: parent, date: date)
            withAnimation(.smooth(duration: 0.3)) { board = fresh }
        } catch {
            failed = true
        }
    }

    /// 加载中的骨架：与真实行同高，数据一到原地替换，避免从转圈到列表的跳变。
    private var skeleton: some View {
        VStack(spacing: 0) {
            ForEach(0..<8, id: \.self) { i in
                HStack(spacing: 8) {
                    RoundedRectangle(cornerRadius: 4).frame(width: 72, height: 16)
                    RoundedRectangle(cornerRadius: 4).frame(width: 28, height: 12)
                    Spacer()
                    RoundedRectangle(cornerRadius: 4).frame(width: 58, height: 14)
                    RoundedRectangle(cornerRadius: 2).frame(width: 44, height: 4)
                }
                .padding(.horizontal, 14).padding(.vertical, 12)
                if i < 7 { Divider().overlay(Theme.border).padding(.leading, 14) }
            }
        }
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .foregroundColor(Theme.textSecondary.opacity(0.18))
        .redacted(reason: .placeholder)
        .accessibilityHidden(true)
    }

    // MARK: - 顶部 / 底部

    /// 顶部只留一件事：数据是哪天收盘的。
    private func summary(_ board: SectorBoard) -> some View {
        HStack(spacing: 8) {
            if let asOf = board.asOf {
                Text(L("%@ 收盘 · 近 20 日相对大盘", asOf))
                    .font(.caption).foregroundColor(Theme.textSecondary)
                    .lineLimit(1).minimumScaleFactor(0.8)
            }
            Spacer(minLength: 8)
            // 用当前最强的行业当例子，讲「相对强弱」和「行业状态」是怎么来的
            if parent == nil, let top = board.sectors.first {
                let derived = MacroDerivations.sector(top, market: market)
                DerivationLink(title: L("行业强弱怎么算的"), conclusion: derived.conclusion, steps: derived.steps, caveat: derived.caveat)
            }
        }
        .padding(.horizontal, 2)
    }

    /// 说明文字退到底部：怎么排的、点行业会怎样、免责。
    private var footer: some View {
        VStack(alignment: .leading, spacing: 4) {
            if parent == nil, let radar {
                Text(radar.eventWords.map { String(format: $0.note, radar.universeName, radar.date) }
                     ?? L("买卖点为%@ %@ 的雷达统计；点行业即在雷达上只看该行业。", radar.universeName, radar.date))
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
            HStack(spacing: 8) {
                Text(L("全部行业")).font(.body.weight(.semibold)).foregroundColor(Theme.textPrimary)
                if selected {
                    Image(systemName: "checkmark.circle.fill").font(.subheadline).foregroundColor(Theme.accent)
                }
                Spacer(minLength: 8)
                countText(buy: buys, sell: sells, words: radar.eventWords.map { (up: $0.up, down: $0.down) })
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(selected ? Theme.accent.opacity(0.12) : Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .contentShape(Rectangle())
        }
        .buttonStyle(RowPressStyle())
        .sensoryFeedback(.selection, trigger: selected)
        .accessibilityHint(L("雷达显示全部行业的信号"))
    }

    /// 买卖点数（基本面 tab 为升降档数）：红买绿卖的小字，没有就不画。
    @ViewBuilder
    private func countText(buy: Int, sell: Int, words: (up: String, down: String)? = nil) -> some View {
        if buy + sell > 0 {
            HStack(spacing: 6) {
                if buy > 0 { Text(words.map { "\(buy) \($0.up)" } ?? L("%lld 买", buy)).foregroundColor(Theme.up) }
                if sell > 0 { Text(words.map { "\(sell) \($0.down)" } ?? L("%lld 卖", sell)).foregroundColor(Theme.down) }
            }
            .font(.caption2.weight(.semibold).monospacedDigit())
        }
    }

    // MARK: - 行

    /// 所有行业一张卡，按相对大盘强弱从强到弱（正负由颜色与强弱条区分，不再分跑赢 / 跑输两组）。
    private func list(_ rows: [SectorRow], maxAbs: Double) -> some View {
        VStack(spacing: 0) {
            ForEach(rows) { row in
                rowView(row, maxAbs: maxAbs)
                if row.id != rows.last?.id { Divider().overlay(Theme.border).padding(.leading, 14) }
            }
        }
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    /// 单行：行业名 + 状态文字 ……… 买卖点 · 强弱值 + 强弱条。一行约 40pt，半屏就能看到大半。
    @ViewBuilder
    private func rowView(_ row: SectorRow, maxAbs: Double) -> some View {
        let selected = parent == nil && radar?.selectedKey == row.key
        let rs = row.rsVsMarket
        let counts = parent == nil ? radar?.counts[row.key] : nil
        let content = HStack(spacing: 8) {
            Text(row.name).font(.body.weight(.semibold)).foregroundColor(Theme.textPrimary)
                .lineLimit(1).minimumScaleFactor(0.8)
            if let label = row.label {
                Text(Self.labelText(label)).font(.caption)
                    .foregroundColor(MarketHeader.regimeColor(label))
                    .lineLimit(1)
            }
            if selected {
                Image(systemName: "checkmark.circle.fill").font(.subheadline).foregroundColor(Theme.accent)
            }
            Spacer(minLength: 6)
            countText(buy: counts?["buy"] ?? 0, sell: counts?["sell"] ?? 0, words: radar?.eventWords.map { (up: $0.up, down: $0.down) })
            // 没有强弱数据（A 股 / 港股的本土行业）就不画强弱值与强弱条，只留买卖点数
            if let rs {
                Text(SectorBoardList.rsText(rs))
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                    .foregroundColor(rs >= 0 ? Theme.up : Theme.down)
                    .lineLimit(1)
                    .frame(minWidth: 58, alignment: .trailing)
                    .contentTransition(.numericText())
                StrengthBar(value: rs, maxAbs: maxAbs)
                    .frame(width: 44, height: 4)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .contentShape(Rectangle())
        .background(selected ? Theme.accent.opacity(0.12) : Color.clear)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(row.label.map { "\(row.name) \(Self.labelText($0)) \(SectorBoardList.rsText(rs))" } ?? row.name)

        if parent == nil {
            Button {
                onPick(row.key, row.name)
            } label: { content }
            .buttonStyle(RowPressStyle())
            .sensoryFeedback(.selection, trigger: selected)
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
    @State private var grown = false

    var body: some View {
        GeometryReader { geo in
            let half = geo.size.width / 2
            let len = half * CGFloat(min(abs(value) / maxAbs, 1)) * (grown ? 1 : 0)
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.textSecondary.opacity(0.15))
                Capsule()
                    .fill(value >= 0 ? Theme.up : Theme.down)
                    .frame(width: max(len, 2))
                    .offset(x: value >= 0 ? half : half - len)
                Rectangle().fill(Theme.textSecondary.opacity(0.5)).frame(width: 1).offset(x: half)
            }
        }
        .animation(.smooth(duration: 0.4), value: value)
        .onAppear { withAnimation(.smooth(duration: 0.5).delay(0.05)) { grown = true } }
        .accessibilityHidden(true)
    }
}

/// 行的按压反馈：按下时底色微亮、轻微缩小，松手弹回。
private struct RowPressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(configuration.isPressed ? Theme.textPrimary.opacity(0.06) : Color.clear)
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
            .animation(.snappy(duration: 0.18), value: configuration.isPressed)
    }
}
