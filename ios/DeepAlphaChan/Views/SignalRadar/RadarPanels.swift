import SwiftUI

/// 雷达页的底部面板：点「行业」格或扇区标签 → 行业面板；点「当日信号」格 → 信号列表。
/// 点气泡、或面板里的某一行，都直接进这只股票的缠论详情页（2026-10-05 起不再先弹「大盘 / 行业 / 结构 / 基本面」
/// 四层事实页——多一层页面只是把详情页里已有的内容再摘一遍）。
///
/// 只陈列事实、不下结论：不出现「同向 / 一致 / 推荐」这类判断。

/// 雷达页正在打开的面板。
enum RadarPanel: Identifiable, Equatable {
    case environment
    /// 选行业：顶部「行业」卡片打开，选了雷达只看该行业。
    case sectorPicker
    case sector(String)
    case signals
    /// 好股票名单：当前综合等级达标的股票，各自有没有买卖点。
    case goodStocks
    /// 基本面动向名单：当前类别（预期上调 / 评级改善）的全部公司与各自的变化。
    case trendList

    var id: String {
        switch self {
        case .environment: return "environment"
        case .sectorPicker: return "sector-picker"
        case .sector(let key): return "sector-\(key)"
        case .signals: return "signals"
        case .goodStocks: return "good-stocks"
        case .trendList: return "trend-list"
        }
    }
}

/// 面板共用的当日事实：选中日的信号、行业强弱。
struct RadarFactContext {
    let market: StockMarket
    let day: RadarDay
    /// 选中日的行业强弱（没有行业统计 / 还没取到时为 nil）。
    let board: SectorBoard?
    /// 选中日行业从强到弱的 key。
    let order: [String]
    let sectorName: (String) -> String

    func row(_ key: String) -> SectorRow? { board?.sectors.first { $0.key == key } }

    /// 行业名次（1 起）与参与排名的行业数。
    func rank(_ key: String) -> (rank: Int, total: Int)? {
        guard let i = order.firstIndex(of: key) else { return nil }
        return (i + 1, order.count)
    }

    func signals(in key: String) -> [RadarSignal] {
        day.signals.filter { ($0.sector ?? SectorRadarLayout.otherKey) == key }
    }

    /// 当天有信号的行业（按强弱从强到弱；不在强弱表里的排后面，「其它」最后）。
    var sectorsWithSignals: [String] {
        let present = Set(day.signals.map { $0.sector ?? SectorRadarLayout.otherKey })
        let known = order.filter { present.contains($0) }
        let rest = present.subtracting(known).subtracting([SectorRadarLayout.otherKey]).sorted {
            RadarSectorCatalog.order($0) < RadarSectorCatalog.order($1)
        }
        return known + rest + (present.contains(SectorRadarLayout.otherKey) ? [SectorRadarLayout.otherKey] : [])
    }
}

// MARK: - 共用小件

@MainActor
enum RadarPanelStyle {
    /// 「二买 ✓」标签：底色与气泡同一套（方向 + 强弱深浅）。
    static func tag(_ signal: RadarSignal) -> some View {
        // 买卖点标签（一买 / 二卖…）由雷达快照给出、是中文，按 App 语言本地化
        Text(signal.confirmed ? "\(L(signal.label)) ✓" : L(signal.label))
            .font(.system(size: 11, weight: .bold))
            .foregroundColor(.white)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(
                SignalFormatting.radarColor(side: signal.side, depth: SignalFormatting.strengthDepth(signal.signalStrength)),
                in: Capsule())
    }

    static func strengthText(_ strength: String) -> String {
        switch strength {
        case "strong": return L("强")
        case "weak": return L("弱")
        default: return L("中")
        }
    }

    /// 信号日期：查看日当天写「当日」，否则写月-日。
    static func dateText(_ date: String, dayDate: String) -> String {
        date == dayDate ? L("当日") : MarketHeader.monthDay(date)
    }

    static func gradeText(_ signal: RadarSignal) -> String? {
        guard signal.quantStatus != "stale", signal.quantStatus != "missing", let g = signal.quantGrade else { return nil }
        return g
    }
}

/// 列表里的一行信号：代码 / 名称 / 类型标签 / 行业 · 强弱 · 评级 / 出现日期。
struct RadarSignalRow: View {
    let signal: RadarSignal
    let dayDate: String
    let sectorName: String?
    let sectorLabel: String?

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(signal.symbol).font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                    if !signal.name.isEmpty {
                        Text(signal.name).font(.caption).foregroundColor(Theme.textSecondary).lineLimit(1)
                    }
                }
                HStack(spacing: 5) {
                    if let sectorName {
                        Circle().fill(MarketHeader.regimeColor(sectorLabel)).frame(width: 6, height: 6)
                        Text(sectorName)
                        Text("·")
                    }
                    Text(L("强弱 %@", RadarPanelStyle.strengthText(signal.signalStrength)))
                    if !signal.confirmed {
                        Text("·")
                        Text(L("未确认"))
                    }
                    if let grade = RadarPanelStyle.gradeText(signal) {
                        Text("·")
                        Text(grade).monospacedDigit()
                    }
                }
                .font(.caption2)
                .foregroundColor(Theme.textSecondary)
                .lineLimit(1)
            }
            Spacer(minLength: 6)
            VStack(alignment: .trailing, spacing: 4) {
                RadarPanelStyle.tag(signal)
                Text(RadarPanelStyle.dateText(signal.date, dayDate: dayDate))
                    .font(.caption2.monospacedDigit()).foregroundColor(Theme.textSecondary)
            }
            Image(systemName: "chevron.right")
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(Theme.textSecondary.opacity(0.6))
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .contentShape(Rectangle())
    }
}

/// 一组信号行（圆角卡片 + 分隔线），每行点一下直接进缠论详情页。
private struct RadarSignalCard: View {
    let signals: [RadarSignal]
    let context: RadarFactContext
    let onOpenDetail: (RadarSignal) -> Void

    var body: some View {
        VStack(spacing: 0) {
            ForEach(signals) { s in
                Button { onOpenDetail(s) } label: {
                    RadarSignalRow(signal: s, dayDate: context.day.date,
                                   sectorName: s.sector.map(context.sectorName),
                                   sectorLabel: s.sector.flatMap { context.row($0)?.label })
                }
                .buttonStyle(.plain)
                if s.id != signals.last?.id { Divider().overlay(Theme.border).padding(.leading, 12) }
            }
        }
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

// MARK: - 行业面板

/// 行业面板：顶部一排行业切换（按强弱排）→ 状态 / 名次 / 相对大盘强弱条 → 该行业当日全部信号 → 细分行业。
struct RadarSectorSheet: View {
    let context: RadarFactContext
    let onOpenDetail: (RadarSignal) -> Void

    @State private var selected: String
    @Environment(\.dismiss) private var dismiss

    init(context: RadarFactContext, initialKey: String, onOpenDetail: @escaping (RadarSignal) -> Void) {
        self.context = context
        self.onOpenDetail = onOpenDetail
        _selected = State(initialValue: initialKey)
    }

    /// 切换条：强弱表里的全部行业（没有信号的也列出、调暗），再补上有信号但不在表里的。
    private var keys: [String] {
        let withSignals = context.sectorsWithSignals
        return context.order + withSignals.filter { !context.order.contains($0) }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    switcher
                    header
                    signalsSection
                    links
                    Text(L("以上为行业与信号的事实陈列，不构成投资建议。"))
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                }
                .padding(16)
            }
            .background(Theme.background)
            .navigationTitle(L("行业 · %@ 收盘", MarketHeader.monthDay(context.day.date)))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button(L("关闭")) { dismiss() } } }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }

    private var switcher: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(keys, id: \.self) { key in
                        let on = key == selected
                        let count = context.signals(in: key).count
                        Button { selected = key } label: {
                            HStack(spacing: 4) {
                                if !on, let label = context.row(key)?.label {
                                    Circle().fill(MarketHeader.regimeColor(label)).frame(width: 6, height: 6)
                                }
                                Text(context.sectorName(key)).font(.system(size: 12, weight: .semibold))
                                if let rs = context.row(key)?.rsVsMarket {
                                    Text(SectorBoardList.rsText(rs)).font(.system(size: 11).monospacedDigit())
                                }
                            }
                            .foregroundColor(on ? .white : Theme.textPrimary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(on ? Theme.accent : Theme.surface, in: Capsule())
                            .overlay(Capsule().stroke(on ? Color.clear : Theme.border, lineWidth: 0.8))
                            .opacity(count == 0 && !on ? 0.5 : 1)
                        }
                        .buttonStyle(.plain)
                        .id(key)
                        .accessibilityAddTraits(on ? [.isSelected] : [])
                    }
                }
                .padding(.horizontal, 1)
            }
            .onAppear { proxy.scrollTo(selected, anchor: .center) }
            .onChange(of: selected) { _, key in
                withAnimation(.easeInOut(duration: 0.2)) { proxy.scrollTo(key, anchor: .center) }
            }
        }
        .sensoryFeedback(.selection, trigger: selected)
    }

    @ViewBuilder
    private var header: some View {
        let row = context.row(selected)
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(context.sectorName(selected))
                    .font(.title3.bold()).foregroundColor(Theme.textPrimary)
                if let label = row?.label {
                    Text(SectorBoardList.labelText(label))
                        .font(.subheadline.weight(.semibold)).foregroundColor(MarketHeader.regimeColor(label))
                }
                if let r = context.rank(selected) {
                    Text(L("第 %lld / %lld", r.rank, r.total))
                        .font(.subheadline).foregroundColor(Theme.textSecondary)
                }
            }
            if let rs = row?.rsVsMarket {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(L("相对大盘")).font(.caption).foregroundColor(Theme.textSecondary)
                        Spacer()
                        Text(SectorBoardList.rsText(rs))
                            .font(.caption.bold().monospacedDigit())
                            .foregroundColor(rs >= 0 ? Theme.up : Theme.down)
                    }
                    ZeroCenteredBar(value: rs, maxAbs: maxAbs).frame(height: 6)
                }
            } else if selected != SectorRadarLayout.otherKey {
                Text(L("这一天的行业强弱还没有数据。")).font(.caption).foregroundColor(Theme.textSecondary)
            } else {
                Text(L("没有行业分类的股票。")).font(.caption).foregroundColor(Theme.textSecondary)
            }
        }
    }

    private var maxAbs: Double {
        max(context.board?.sectors.compactMap { $0.rsVsMarket.map(abs) }.max() ?? 0, 0.0001)
    }

    @ViewBuilder
    private var signalsSection: some View {
        let list = context.signals(in: selected)
        let buys = list.filter(\.isBuy).count
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(L("在场信号 %lld 个 · %lld 买 %lld 卖", list.count, buys, list.count - buys))
                    .font(.footnote.weight(.semibold)).foregroundColor(Theme.textSecondary)
                Spacer()
                Text(L("按出现时间，最新在前")).font(.caption2).foregroundColor(Theme.textSecondary)
            }
            if list.isEmpty {
                Text(L("这一天该行业没有在场的买卖点。"))
                    .font(.footnote).foregroundColor(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
                    .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
            } else {
                RadarSignalCard(signals: list, context: context, onOpenDetail: onOpenDetail)
            }
        }
    }

    @ViewBuilder
    private var links: some View {
        VStack(spacing: 0) {
            if context.row(selected)?.hasChildren == true {
                NavigationLink {
                    SectorBoardList(market: context.market, date: context.day.date, parent: selected,
                                    parentName: context.sectorName(selected), radar: nil) { _, _ in }
                } label: { linkLabel(L("细分行业")) }
                Divider().overlay(Theme.border).padding(.leading, 12)
            }
            if context.board != nil {
                NavigationLink {
                    SectorBoardList(market: context.market, date: context.day.date, parent: nil, parentName: nil,
                                    radar: nil) { _, _ in }
                } label: { linkLabel(L("全部行业强弱")) }
            }
        }
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func linkLabel(_ title: String) -> some View {
        HStack {
            Text(title).font(.footnote).foregroundColor(Theme.accent)
            Spacer()
            Image(systemName: "chevron.right").font(.system(size: 10, weight: .semibold)).foregroundColor(Theme.accent)
        }
        .padding(12)
        .contentShape(Rectangle())
    }
}

/// 以 0 为中线的强弱条：跑赢向右（红）、跑输向左（绿）。
struct ZeroCenteredBar: View {
    let value: Double
    let maxAbs: Double

    var body: some View {
        GeometryReader { geo in
            let half = geo.size.width / 2
            let len = half * CGFloat(min(abs(value) / max(maxAbs, 0.0001), 1))
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

// MARK: - 信号列表

/// 当日全部在场信号（按出现时间，最新在前），可按买 / 卖、一二三类筛。
struct RadarSignalListSheet: View {
    let context: RadarFactContext
    let universeName: String
    let onOpenDetail: (RadarSignal) -> Void

    /// 当前筛选：nil = 全部；否则只看某一种买卖点（一买 / 二买 / 三买 / 一卖 / 二卖 / 三卖）。
    @State private var kind: Kind?
    @Environment(\.dismiss) private var dismiss

    private struct Kind: Hashable {
        let side: String
        let level: Int

        var title: String {
            let i = max(0, min(level, 3) - 1)
            return side == "buy" ? L(["一买", "二买", "三买"][i]) : L(["一卖", "二卖", "三卖"][i])
        }
    }

    private static let kinds: [Kind] = ["buy", "sell"].flatMap { side in (1...3).map { Kind(side: side, level: $0) } }

    private func matches(_ s: RadarSignal, _ k: Kind?) -> Bool {
        guard let k else { return true }
        return s.side == k.side && s.level == k.level
    }

    private var filtered: [RadarSignal] {
        context.day.signals.filter { matches($0, kind) }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    filters
                    Text(L("%@ · 近 5 个交易日内出现、尚未被收盘价跌破（卖点：涨破）的全部信号，按出现时间排。",
                           universeName))
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    if filtered.isEmpty {
                        Text(L("没有符合条件的信号。"))
                            .font(.footnote).foregroundColor(Theme.textSecondary)
                            .frame(maxWidth: .infinity).padding(.top, 30)
                    } else {
                        RadarSignalCard(signals: filtered, context: context, onOpenDetail: onOpenDetail)
                    }
                }
                .padding(16)
            }
            .background(Theme.background)
            .navigationTitle(L("%@ 的在场信号 · %lld 个", MarketHeader.monthDay(context.day.date), context.day.signals.count))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button(L("关闭")) { dismiss() } } }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
    }

    /// 一行单选：全部 / 一买 / 二买 / 三买 / 一卖 / 二卖 / 三卖，各带个数；当天没有的那种不显示。
    private var filters: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                chip(L("全部 %lld", context.day.signals.count), on: kind == nil) { kind = nil }
                ForEach(Self.kinds, id: \.self) { k in
                    let n = context.day.signals.filter { matches($0, k) }.count
                    if n > 0 {
                        chip("\(k.title) \(n)", on: kind == k) { kind = kind == k ? nil : k }
                    }
                }
            }
        }
    }

    private func chip(_ title: String, on: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 12, weight: on ? .semibold : .regular))
                .foregroundColor(on ? .white : Theme.textSecondary)
                .padding(.horizontal, 11)
                .padding(.vertical, 6)
                .background(on ? Theme.accent : Color.clear, in: Capsule())
                .overlay(Capsule().stroke(on ? Color.clear : Theme.border, lineWidth: 0.8))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? [.isSelected] : [])
    }
}
