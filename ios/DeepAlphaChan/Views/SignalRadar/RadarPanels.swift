import SwiftUI

/// 雷达页的底部面板：点「行业」格或扇区标签 → 行业面板；点「当日信号」格 → 信号列表；
/// 点气泡（或面板里的某一行）→ 这只股票的四层事实（大盘 / 行业 / 结构 / 基本面）。
///
/// 全部留在雷达页里讲完，只陈列事实、不下结论：不出现「同向 / 一致 / 推荐」这类判断，
/// 「查看K线与结构详情」才进详情页（详情页不变）。

/// 雷达页正在打开的面板。
enum RadarPanel: Identifiable, Equatable {
    case environment
    case sector(String)
    case signals
    case signal(RadarSignal)

    var id: String {
        switch self {
        case .environment: return "environment"
        case .sector(let key): return "sector-\(key)"
        case .signals: return "signals"
        case .signal(let s): return "signal-\(s.id)"
        }
    }
}

/// 面板共用的当日事实：选中日的信号、行业强弱、大盘状态与情绪。
struct RadarFactContext {
    let market: StockMarket
    let day: RadarDay
    /// 选中日的行业强弱（没有行业统计 / 还没取到时为 nil）。
    let board: SectorBoard?
    /// 选中日行业从强到弱的 key。
    let order: [String]
    let macro: MacroState?
    let panic: PanicIndexResponse?
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

enum RadarPanelStyle {
    /// 「二买 ✓」标签：底色与气泡同一套（方向 + 强弱深浅）。
    static func tag(_ signal: RadarSignal) -> some View {
        Text(signal.confirmed ? "\(signal.label) ✓" : signal.label)
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

/// 一组信号行（圆角卡片 + 分隔线），每行点进四层事实。
private struct RadarSignalCard: View {
    let signals: [RadarSignal]
    let context: RadarFactContext

    var body: some View {
        VStack(spacing: 0) {
            ForEach(signals) { s in
                NavigationLink(value: s) {
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
            .navigationDestination(for: RadarSignal.self) { s in
                RadarSignalFactView(signal: s, context: context, onOpenDetail: onOpenDetail)
            }
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
                RadarSignalCard(signals: list, context: context)
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

    @State private var side: String?
    @State private var level: Int?
    @Environment(\.dismiss) private var dismiss

    private var filtered: [RadarSignal] {
        context.day.signals.filter { s in
            (side == nil || s.side == side) && (level == nil || s.level == level)
        }
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
                        RadarSignalCard(signals: filtered, context: context)
                    }
                }
                .padding(16)
            }
            .background(Theme.background)
            .navigationTitle(L("%@ 的在场信号 · %lld 个", MarketHeader.monthDay(context.day.date), context.day.signals.count))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button(L("关闭")) { dismiss() } } }
            .navigationDestination(for: RadarSignal.self) { s in
                RadarSignalFactView(signal: s, context: context, onOpenDetail: onOpenDetail)
            }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
    }

    private var filters: some View {
        let buys = context.day.signals.filter(\.isBuy).count
        let sells = context.day.signals.count - buys
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                chip(L("全部"), on: side == nil) { side = nil }
                chip(L("买 %lld", buys), on: side == "buy") { side = side == "buy" ? nil : "buy" }
                chip(L("卖 %lld", sells), on: side == "sell") { side = side == "sell" ? nil : "sell" }
                Rectangle().fill(Theme.border).frame(width: 1, height: 16).padding(.horizontal, 2)
                chip(L("一类"), on: level == 1) { level = level == 1 ? nil : 1 }
                chip(L("二类"), on: level == 2) { level = level == 2 ? nil : 2 }
                chip(L("三类"), on: level == 3) { level = level == 3 ? nil : 3 }
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

// MARK: - 一只股票的四层事实

/// 点气泡后的面板：大盘 / 行业 / 结构 / 基本面四行，只陈列事实；底部按钮进详情页。
struct RadarSignalFactView: View {
    let signal: RadarSignal
    let context: RadarFactContext
    let onOpenDetail: (RadarSignal) -> Void

    @State private var research: QuantResearch?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                header
                VStack(spacing: 0) {
                    factRow(L("大盘"), main: marketMain, sub: marketSub)
                    Divider().overlay(Theme.border)
                    factRow(L("行业"), main: sectorMain, sub: sectorSub)
                    Divider().overlay(Theme.border)
                    factRow(L("结构"), main: structureMain, sub: structureSub)
                    Divider().overlay(Theme.border)
                    factRow(L("基本面"), main: fundamentalMain, sub: fundamentalSub)
                }
                .padding(.horizontal, 12)
                .background(Theme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 12))

                Button { onOpenDetail(signal) } label: {
                    Text(L("查看K线与结构详情"))
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 13)
                        .background(Theme.accent, in: RoundedRectangle(cornerRadius: 12))
                        .foregroundColor(.white)
                }
                .buttonStyle(.plain)

                Text(L("以上为按规则得出的事实陈列，不构成投资建议。"))
                    .font(.caption2).foregroundColor(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
            .padding(16)
        }
        .background(Theme.background)
        .navigationTitle(signal.symbol)
        .navigationBarTitleDisplayMode(.inline)
        .task(id: signal.id) {
            // 只有美股有基本面研究；拉不到就只显示气泡上已有的综合等级
            guard context.market == .us, research == nil else { return }
            research = try? await QuantResearchService.research(market: context.market, symbol: signal.symbol)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(signal.symbol).font(.title2.bold()).foregroundColor(Theme.textPrimary)
                if !signal.name.isEmpty {
                    Text(signal.name).font(.subheadline).foregroundColor(Theme.textSecondary).lineLimit(1)
                }
                Spacer(minLength: 0)
                RadarPanelStyle.tag(signal)
            }
            Text(L("%@ 出现 · 信号价位 %@", signal.date, String(format: "%.2f", signal.price)))
                .font(.caption.monospacedDigit()).foregroundColor(Theme.textSecondary)
        }
    }

    private func factRow(_ title: String, main: String, sub: String?) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(title)
                .font(.caption).foregroundColor(Theme.textSecondary)
                .frame(width: 44, alignment: .leading)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 3) {
                Text(main).font(.subheadline.weight(.semibold)).foregroundColor(Theme.textPrimary)
                if let sub {
                    Text(sub).font(.caption).foregroundColor(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 11)
        .accessibilityElement(children: .combine)
    }

    // MARK: 大盘

    private var marketMain: String {
        guard let m = context.macro else { return L("暂无数据") }
        return L("%@ %lld%%", m.labelText, Int((m.probability * 100).rounded()))
    }

    private var marketSub: String? {
        var parts: [String] = []
        if let m = context.macro { parts.append(L("已持续 %lld 天", m.daysInState)) }
        if let p = context.panic {
            parts.append(L("恐慌贪婪 %lld %@", Int(p.current.score.rounded()), PanicIndexStyle.ratingLabel(p.current.rating)))
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    // MARK: 行业

    private var sectorKey: String { signal.sector ?? SectorRadarLayout.otherKey }

    private var sectorMain: String {
        guard signal.sector != nil else { return L("暂无行业分类") }
        let name = context.sectorName(sectorKey)
        if let rs = context.row(sectorKey)?.rsVsMarket {
            return L("%@ · 相对大盘 %@", name, SectorBoardList.rsText(rs))
        }
        return name
    }

    private var sectorSub: String? {
        guard signal.sector != nil else { return nil }
        var parts: [String] = []
        if let r = context.rank(sectorKey) { parts.append(L("%lld 个行业中第 %lld", r.total, r.rank)) }
        if let label = context.row(sectorKey)?.label { parts.append(L("状态%@", SectorBoardList.labelText(label))) }
        let others = context.signals(in: sectorKey).count - 1
        if others > 0 { parts.append(L("同行业另有 %lld 个在场信号", others)) }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    // MARK: 结构

    private var structureMain: String {
        let state = signal.confirmed ? L("已确认") : L("未确认")
        return L("%@ · %@ · 强弱%@", signal.label, state, RadarPanelStyle.strengthText(signal.signalStrength))
    }

    private var structureSub: String? {
        var parts: [String] = []
        if let label = signal.subLevelLabel, !label.isEmpty { parts.append(L("30 分钟：%@", label)) }
        parts.append(signal.isBuy
                     ? L("收盘价跌破 %@ 即从雷达移出", String(format: "%.2f", signal.price))
                     : L("收盘价涨破 %@ 即从雷达移出", String(format: "%.2f", signal.price)))
        if !signal.confirmed { parts.append(L("所在笔还没走完，之后可能被新K线改写")) }
        return parts.joined(separator: " · ")
    }

    // MARK: 基本面

    private var fundamentalMain: String {
        if let r = research, r.isOK, let grade = r.overall?.grade {
            if let moat = r.moat?.ratingName { return L("综合 %@ · 护城河 %@", grade, moat) }
            return L("综合 %@", grade)
        }
        if let grade = RadarPanelStyle.gradeText(signal) { return L("综合 %@", grade) }
        return context.market == .us ? L("暂无评级") : L("该市场暂未覆盖")
    }

    private var fundamentalSub: String? {
        if let r = research, r.isOK {
            let dims = r.scoredDimensions.compactMap { d in d.grade.map { "\(d.name) \($0)" } }
            if !dims.isEmpty { return dims.joined(separator: " · ") }
        }
        if let asOf = signal.quantAsOf { return L("评级日期 %@", asOf) }
        return nil
    }
}
