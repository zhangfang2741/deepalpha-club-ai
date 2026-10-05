import SwiftUI

/// 自选 Tab：登录用户的关注清单。点一行复用分析 Tab 共享的 `ChanViewModel`
/// 跑一遍缠论分析，进结果页——不新开一套查询逻辑。
///
/// 和雷达同一套语言、同样自上而下：顶部环境横幅（各市场大盘状态）→ 按「近 5 日有信号 / 暂无新信号」
/// 分组 → 每行带行业状态圆点与相对大盘强弱、结构阶段、基本面等级、在场信号。只陈列事实。
struct WatchlistView: View {
    @ObservedObject var chanVM: ChanViewModel
    @StateObject private var vm = WatchlistViewModel()
    @EnvironmentObject private var store: StoreManager

    @State private var showResults = false
    /// 自选现在所有档位都能用（未订阅 1 支 / 会员不限），
    /// 点已满时的「升级解锁更多」入口才弹这个付费墙，不再整体锁死。
    @State private var showPaywall = false
    /// 环境横幅里点某个市场：打开该市场的环境面板（与雷达「环境」格同一个）。
    @State private var envMarket: StockMarket?

    var body: some View {
        NavigationStack {
            content
                .navigationTitle(L("自选"))
                // 与「信号」「我的」等 Tab 一致用小标题；大标题在自选只有一两支时
                // 会在顶部留出一大块空白。
                .navigationBarTitleDisplayMode(.inline)
                .task { await vm.onAppear(tier: store.tier) }
                .onReceive(NotificationCenter.default.publisher(for: .watchlistDidChange)) { _ in
                    Task { await vm.refresh(tier: store.tier) }
                }
                // tier 变化（订阅/升级/降级）后上限可能跟着变，重新拉一次同步。
                .onChange(of: store.tier) { _, tier in
                    Task { await vm.refresh(tier: tier) }
                }
                .navigationDestination(isPresented: $showResults) {
                    if let analysis = chanVM.analysis {
                        ResultDetailView(analysis: analysis, vm: chanVM)
                    }
                }
                .overlay { if chanVM.isLoading { loadingOverlay } }
                .alert(chanVM.errorMessage ?? "", isPresented: Binding(
                    get: { !showResults && chanVM.errorMessage != nil },
                    set: { if !$0 { chanVM.errorMessage = nil } }
                )) {
                    Button(L("好"), role: .cancel) {}
                }
                // 移出自选（滑动删除）失败时的提示——不用等下次下拉刷新才发现没删掉。
                .alert(vm.errorMessage ?? "", isPresented: Binding(
                    get: { vm.errorMessage != nil },
                    set: { if !$0 { vm.errorMessage = nil } }
                )) {
                    Button(L("好"), role: .cancel) {}
                }
                .sheet(isPresented: $showPaywall) { PaywallView() }
                .sheet(item: $envMarket) { MacroDetailSheet(market: $0) }
        }
    }

    // MARK: - 环境横幅

    /// 各市场大盘状态一格一格排开（点开环境面板），下面一行写「几只近 5 日有信号」。
    private var environmentBanner: some View {
        VStack(alignment: .leading, spacing: 6) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(vm.markets) { market in
                        Button { envMarket = market } label: {
                            HStack(spacing: 5) {
                                let state = vm.macro[market]
                                Circle().fill(MarketHeader.regimeColor(state?.label)).frame(width: 7, height: 7)
                                Text(market.title).foregroundColor(Theme.textSecondary)
                                if let state {
                                    Text(L("%@ %lld%%", state.labelText, Int((state.probability * 100).rounded())))
                                        .fontWeight(.semibold)
                                        .foregroundColor(MarketHeader.regimeColor(state.label))
                                } else {
                                    Text("--").foregroundColor(Theme.textSecondary)
                                }
                                Image(systemName: "chevron.right").font(.system(size: 8, weight: .semibold))
                                    .foregroundColor(Theme.textSecondary.opacity(0.7))
                            }
                            .font(.caption)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 7)
                            .background(Theme.surface, in: Capsule())
                            .overlay(Capsule().stroke(Theme.border, lineWidth: 0.8))
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(L("%@市场环境", market.title))
                    }
                }
            }
            if vm.signalsLoaded {
                let withSignals = vm.items.filter { vm.hasSignal($0) }.count
                Text(L("%lld 只自选里 %lld 只近 5 日有在场信号", vm.items.count, withSignals))
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
            }
        }
    }

    /// 自选数量 / 上限，让用户在接近上限前就有数，不用加满了才在报错里第一次看到数字。
    /// 会员不限（maxItems 为 nil）时只显示已收藏数量，不显示「/ 上限」；接近或已达
    /// 上限（未订阅）时额外给一个订阅入口，直接引导订阅而不是让用户自己
    /// 去「我的」页找订阅入口。
    ///
    /// 放在 List 里作为第一行，不能摆在 List 外面：外面的话下拉时大标题和列表一起被
    /// 拉伸，这一行却钉在原地，看起来像飘在半空。
    private var countRow: some View {
        HStack(spacing: 6) {
            Image(systemName: "star.fill")
                .font(.system(size: 11))
                .foregroundColor(vm.isFull ? Theme.segment : Theme.accent)
            if let maxItems = vm.maxItems {
                Text(L("已收藏 %lld / %lld", vm.ownItems.count, maxItems))
                    .foregroundColor(vm.isFull ? Theme.segment : Theme.textSecondary)
            } else {
                Text(L("已收藏 %lld 支", vm.ownItems.count))
                    .foregroundColor(Theme.textSecondary)
            }
            Spacer()
            if !store.isPremium, vm.isFull {
                Button { showPaywall = true } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "crown.fill")
                        Text(L("升级解锁更多"))
                    }
                    .font(.caption.bold())
                    .foregroundColor(.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Theme.segment, in: Capsule())
                }
                .buttonStyle(.plain)
            }
        }
        .font(.footnote)
    }

    /// 非会员只有最早加入的一支能看状态（见 WatchlistViewModel.phase(for:)），
    /// 其余行没有标签——不说明的话，用户只会觉得「状态没渲染出来、下拉也不刷新」。
    private var phaseLockedBanner: some View {
        Button { showPaywall = true } label: {
            HStack(spacing: 8) {
                Image(systemName: "lock.fill").font(.caption)
                Text(L("订阅会员，显示全部自选标的的结构状态"))
                    .font(.caption)
                    .multilineTextAlignment(.leading)
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.caption2)
            }
            .foregroundColor(Theme.segment)
            .padding(.vertical, 10)
            .padding(.horizontal, 12)
            .background(Theme.segment.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var content: some View {
        if vm.isLoading && vm.items.isEmpty {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if vm.items.isEmpty {
            emptyState
        } else {
            list
        }
    }

    /// 按市场分组展示：同一市场排一起，标题栏带数量，比单一长列表更有层次。
    /// 分组顺序固定用 `StockMarket.allCases`（美/A/港），组内保留后端返回顺序
    /// （最近加入的在前，见 `WatchlistViewModel.toggle`）。
    private var groupedItems: [(market: StockMarket, items: [WatchlistItem])] {
        StockMarket.allCases.compactMap { market in
            let matched = vm.items.filter { $0.market == market.rawValue }
            return matched.isEmpty ? nil : (market, matched)
        }
    }

    /// 列表分组：信号拉到之前按市场分组；拉到之后分「近 5 日有信号」（最新在前）与「暂无新信号」。
    private var sections: [(title: String, dot: Color, items: [WatchlistItem])] {
        guard vm.signalsLoaded else {
            return groupedItems.map { (title: $0.market.title, dot: marketColor($0.market), items: $0.items) }
        }
        let active = vm.items.filter { vm.hasSignal($0) }.sorted {
            (vm.signals[$0.id]?.date ?? "") > (vm.signals[$1.id]?.date ?? "")
        }
        let quiet = vm.items.filter { !vm.hasSignal($0) }
        var out: [(title: String, dot: Color, items: [WatchlistItem])] = []
        if !active.isEmpty { out.append((title: L("近 5 日有信号"), dot: Theme.accent, items: active)) }
        if !quiet.isEmpty { out.append((title: L("暂无新信号"), dot: Theme.textSecondary, items: quiet)) }
        return out
    }

    private var list: some View {
        List {
            Section {
                countRow
                    .listRowInsets(EdgeInsets(top: 10, leading: 16, bottom: 6, trailing: 16))
                    .listRowSeparator(.hidden)
                    .listRowBackground(Theme.background)
                if vm.hasLockedPhases {
                    phaseLockedBanner
                        .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 4, trailing: 16))
                        .listRowSeparator(.hidden)
                        .listRowBackground(Theme.background)
                }
                environmentBanner
                    .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 6, trailing: 16))
                    .listRowSeparator(.hidden)
                    .listRowBackground(Theme.background)
            }
            ForEach(sections, id: \.title) { group in
                Section {
                    ForEach(group.items) { item in
                        Button {
                            open(item)
                        } label: {
                            row(item, market: StockMarket(rawValue: item.market) ?? .us)
                        }
                        .buttonStyle(.plain)
                        .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 4, trailing: 16))
                        .listRowSeparator(.hidden)
                        .listRowBackground(Theme.background)
                        // 左滑只露垃圾桶图标，不显示「删除」文字；Label 保留文字给 VoiceOver 读。
                        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                            Button(role: .destructive) {
                                Task { await vm.remove(item, tier: store.tier) }
                            } label: {
                                Label(L("移出自选"), systemImage: "trash")
                                    .labelStyle(.iconOnly)
                            }
                        }
                    }
                } header: {
                    HStack(spacing: 6) {
                        Circle().fill(group.dot).frame(width: 6, height: 6)
                        Text(group.title)
                        Text("· \(group.items.count)")
                            .foregroundColor(Theme.textSecondary)
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundColor(Theme.textPrimary)
                    // plain 列表的分组标题自带一层灰色底，和页面背景不一致；铺满自己的底色盖掉。
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 16)
                    .padding(.top, 10)
                    .padding(.bottom, 4)
                    .background(Theme.background)
                    .listRowInsets(EdgeInsets())
                }
                .textCase(nil)
            }
            // 列表末尾的操作提示：自选只有一两支时页面下半截不至于一片空白，
            // 也顺带告诉用户怎么加、怎么删。
            Text(L("在分析结果页点 ☆ 加入自选，左滑可移出"))
                .font(.caption2)
                .foregroundColor(Theme.textSecondary)
                .frame(maxWidth: .infinity)
                .listRowInsets(EdgeInsets(top: 16, leading: 16, bottom: 16, trailing: 16))
                .listRowSeparator(.hidden)
                .listRowBackground(Theme.background)
        }
        .listStyle(.plain)
        // 隐藏系统列表底色，整页统一用主题背景——否则列表是纯黑、行是主题深灰，
        // 每一行都像一条色带。
        .scrollContentBackground(.hidden)
        .background(Theme.background)
        // 去掉系统默认 44pt 最小行高，计数行才能紧凑。
        .environment(\.defaultMinListRowHeight, 0)
        .refreshable { await vm.refresh(tier: store.tier) }
    }

    /// 各市场一个基调色，纯粹用来在自选列表里做视觉区分（左侧色条 + 圆点），
    /// 跟涨跌色无关，不复用 Theme.up/down 避免用户误读成涨跌方向。
    private func marketColor(_ market: StockMarket) -> Color {
        switch market {
        case .us: return Theme.accent
        case .cn: return .orange
        case .hk: return .purple
        }
    }

    private func row(_ item: WatchlistItem, market: StockMarket) -> some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 2)
                .fill(marketColor(market))
                .frame(width: 3, height: 32)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(item.symbol)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(Theme.textPrimary)
                    // 默认送的示例股：不占名额、免额度、可看完整次级别；与雷达示例日同一种标记
                    if item.isSample {
                        Text(L("示例"))
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(Theme.segment)
                            .padding(.horizontal, 5).padding(.vertical, 1)
                            .overlay(Capsule().stroke(Theme.segment.opacity(0.7), lineWidth: 0.8))
                    }
                    // 基本面综合等级：没有评级（港股 / A 股、过期）就不显示，不放破折号占位
                    if let grade = item.quantGrade {
                        let color = QuantGradeStyle.color(grade)
                        Text(grade)
                            .font(.system(size: 10, weight: .bold, design: .rounded))
                            .foregroundStyle(color)
                            .padding(.horizontal, 5).padding(.vertical, 1)
                            .background(color.opacity(0.13), in: RoundedRectangle(cornerRadius: 4))
                            .accessibilityLabel(L("基本面等级 %@", grade))
                    }
                }
                // 名称（有别于代码才显示）· 行业状态圆点 + 行业名 + 相对大盘
                HStack(spacing: 5) {
                    if let name = item.displayName {
                        Text(name).lineLimit(1)
                    }
                    if let key = item.sector {
                        let row = vm.sectorRows[key]
                        if item.displayName != nil { Text("·") }
                        Circle().fill(MarketHeader.regimeColor(row?.label)).frame(width: 6, height: 6)
                        Text(row?.name ?? RadarSectorCatalog.name(key)).lineLimit(1)
                        if let rs = row?.rsVsMarket {
                            Text(SectorBoardList.rsText(rs))
                                .monospacedDigit()
                                .foregroundColor(rs >= 0 ? Theme.up : Theme.down)
                        }
                    }
                }
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
            }
            Spacer()
            if let phase = vm.phase(for: item), let label = phase.phaseLabel {
                Chip(text: label, color: Theme.phaseColor(phase: phase.phase, direction: phase.direction))
            }
            if let sig = vm.signal(for: item) {
                // 在场信号：与雷达气泡同一套颜色；日期是信号出现那天
                VStack(alignment: .trailing, spacing: 3) {
                    RadarPanelStyle.tag(sig)
                    Text(MarketHeader.monthDay(sig.date))
                        .font(.caption2.monospacedDigit())
                        .foregroundColor(Theme.textSecondary)
                }
            } else if vm.hasSignal(item) {
                // 有信号但当前档位看不到（与结构状态同一道门槛）
                Image(systemName: "lock.fill")
                    .font(.caption2)
                    .foregroundColor(Theme.segment)
                    .accessibilityLabel(L("有在场信号，升级后可见"))
            } else {
                Text(relativeTime(item.createdAt))
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
            }
            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 12)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private static let isoFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let isoFormatterNoFraction = ISO8601DateFormatter()
    private static let relativeFormatter: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter()
        f.locale = Locale.current
        f.unitsStyle = .short
        return f
    }()

    /// 加入时间转成「3 天前」这类相对时间，比一串 ISO 时间戳更容易一眼扫过去。
    private func relativeTime(_ raw: String) -> String {
        let date = Self.isoFormatter.date(from: raw) ?? Self.isoFormatterNoFraction.date(from: raw)
        guard let date else { return "" }
        return Self.relativeFormatter.localizedString(for: date, relativeTo: Date())
    }

    private var emptyState: some View {
        VStack(spacing: 14) {
            ZStack {
                Circle().fill(Theme.surface).frame(width: 72, height: 72)
                Image(systemName: "star.fill")
                    .font(.system(size: 28))
                    .foregroundColor(Theme.accent)
            }
            Text(L("还没有自选"))
                .font(.subheadline.bold())
                .foregroundColor(Theme.textPrimary)
            Text(L("在缠论分析结果页点星标即可加入，方便随时回来看结构变化"))
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.background)
    }

    private var loadingOverlay: some View {
        ZStack {
            Theme.background.opacity(0.85).ignoresSafeArea()
            VStack(spacing: 12) {
                ProgressView().tint(Theme.accent)
                Text(L("正在拉取行情并计算缠论结构…"))
                    .font(.subheadline).foregroundColor(Theme.textSecondary)
            }
        }
    }

    private func open(_ item: WatchlistItem) {
        guard let market = StockMarket(rawValue: item.market) else { return }
        chanVM.apply(market: market, symbol: item.symbol, name: item.displayName)
        Task {
            await chanVM.runAnalysis()
            if chanVM.errorMessage == nil, chanVM.analysis != nil {
                showResults = true
            }
        }
    }
}
