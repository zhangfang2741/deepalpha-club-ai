import SwiftUI

/// 自选 Tab：登录用户的关注清单。点一行复用分析 Tab 共享的 `ChanViewModel`
/// 跑一遍缠论分析，进结果页——不新开一套查询逻辑，和「信号」页点气泡跳转分析
/// 是同一个模式。
struct WatchlistView: View {
    @ObservedObject var chanVM: ChanViewModel
    @StateObject private var vm = WatchlistViewModel()
    @EnvironmentObject private var store: StoreManager

    @State private var showResults = false
    /// 自选是高级版专属功能；非高级版看到的是 lockedView，点它弹这个付费墙。
    @State private var showPaywall = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if !store.isPremium {
                    lockedView
                } else {
                    if !vm.items.isEmpty { countRow }
                    content
                }
            }
                .navigationTitle(L("自选"))
                .task { if store.isPremium { await vm.onAppear() } }
                .onReceive(NotificationCenter.default.publisher(for: .watchlistDidChange)) { _ in
                    guard store.isPremium else { return }
                    Task { await vm.refresh() }
                }
                // 付费墙里订阅成功后，立刻拉一次自选列表，不用退出再进这个 Tab。
                .onChange(of: store.isPremium) { _, isPremium in
                    guard isPremium else { return }
                    Task { await vm.refresh() }
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
        }
    }

    /// 未订阅高级版时替代自选内容展示的锁定态：说明权益 + 升级入口，
    /// 与信号雷达 SignalRadarView.lockedView 同一视觉语言。
    private var lockedView: some View {
        VStack(spacing: 14) {
            Image(systemName: "star.fill")
                .font(.system(size: 40)).foregroundColor(Theme.segment)
            Text(L("自选是高级版专属功能"))
                .font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
            Text(L("关注的标的批量算出当前结构阶段，订阅高级版解锁"))
                .font(.footnote).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 30)
            Button { showPaywall = true } label: {
                Label(L("升级高级版"), systemImage: "crown.fill")
                    .font(.subheadline.bold())
                    .padding(.horizontal, 20).padding(.vertical, 10)
                    .background(Theme.accent).foregroundColor(.white)
                    .clipShape(Capsule())
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// 自选数量 / 上限，让用户在接近 20 支上限前就有数，不用加满了才在报错里第一次看到数字。
    private var countRow: some View {
        HStack {
            Text(L("已收藏 %lld / %lld", vm.items.count, vm.maxItems))
                .font(.caption2)
                .foregroundColor(vm.isFull ? Theme.segment : Theme.textSecondary)
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.top, 8)
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

    private var list: some View {
        List {
            ForEach(groupedItems, id: \.market) { group in
                Section {
                    ForEach(group.items) { item in
                        Button {
                            open(item)
                        } label: {
                            row(item, market: group.market)
                        }
                        .buttonStyle(.plain)
                        .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 4, trailing: 16))
                        .listRowSeparator(.hidden)
                        .listRowBackground(Theme.background)
                    }
                    .onDelete { offsets in
                        for index in offsets {
                            let item = group.items[index]
                            Task { await vm.remove(item) }
                        }
                    }
                } header: {
                    HStack(spacing: 6) {
                        Circle().fill(marketColor(group.market)).frame(width: 6, height: 6)
                        Text(group.market.title)
                        Text("· \(group.items.count)")
                            .foregroundColor(Theme.textSecondary)
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundColor(Theme.textPrimary)
                }
                .textCase(nil)
            }
        }
        .listStyle(.plain)
        .refreshable { await vm.refresh() }
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
                Text(item.symbol)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Theme.textPrimary)
                // 只有拿到真正的名称（有别于代码）才显示副标题，否则不再原样重复代码。
                if let name = item.displayName {
                    Text(name)
                        .font(.caption)
                        .foregroundColor(Theme.textSecondary)
                        .lineLimit(1)
                }
            }
            Spacer()
            if let phase = vm.phases[item.id], let label = phase.phaseLabel {
                Chip(text: label, color: Theme.pivotPhaseColor(phase.phase))
            }
            Text(relativeTime(item.createdAt))
                .font(.caption2)
                .foregroundColor(Theme.textSecondary)
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
