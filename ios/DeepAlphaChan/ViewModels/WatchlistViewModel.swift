import Foundation

extension Notification.Name {
    /// 自选变更广播：加入/移出任一端触发后发出，另一端（不同 WatchlistViewModel
    /// 实例）借此知道要重新拉一次，而不是等下次 `onAppear` 里 `items.isEmpty`
    /// 判断失效才刷新——那样分析详情页加完星标切回自选 Tab 会看到旧列表。
    static let watchlistDidChange = Notification.Name("watchlistDidChange")
}

/// 自选股状态：拉取列表、加入/移出、判断某个 market+symbol 是否已在自选里。
///
/// 「自选」Tab 和分析结果页的星标按钮各自持有一份实例（见 ResultDetailView），
/// 不共享同一个对象——两边都直接对后端做加/删，靠 `.watchlistDidChange` 广播
/// 通知对方重新 `refresh()` 来同步，不需要把同一个实例一路传下去。
@MainActor
final class WatchlistViewModel: ObservableObject {
    @Published private(set) var items: [WatchlistItem] = []
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?
    /// 每只自选标的当前的中枢阶段，key 为 `WatchlistItem.id`（`{market}:{symbol}`）。
    /// 「自选批量状态计算」是高级版专属权益（见 PaywallView 的高级版权益列表），
    /// 只在「自选」Tab 的 `refresh()`/`onAppear()` 里、且 tier 为 premium 时才拉；
    /// `refreshSilently()`（给分析详情页星标按钮判断收藏状态用）不拉——那条路径要快，
    /// 多算全部标的的缠论阶段没必要也拖慢它。取不到的标的直接没有 key，UI 不显示标签。
    @Published private(set) var phases: [String: WatchlistPhase] = [:]
    private var isLoadingPhases = false

    private var memberships: Set<String> = []

    /// 自选上限，从 `GET /watchlist` 的 `max_items` 同步，不在端上硬编码——
    /// 改上限只用改后端 `app.services.watchlist.TIER_LIMITS` 一处。nil 表示不限
    /// （高级版）；1 是加载前的合理默认值，与未订阅档位一致。
    @Published private(set) var maxItems: Int? = 1
    var isFull: Bool {
        guard let maxItems else { return false }
        return items.count >= maxItems
    }

    func isStarred(market: StockMarket, symbol: String) -> Bool {
        memberships.contains(Self.key(market: market, symbol: symbol))
    }

    /// 每次切到自选页都重算阶段（行情每天在变，之前只在列表为空时加载，切回来标签不更新、
    /// 只能手动下拉）。首次带 loading 完整加载；已有数据时静默刷新列表 + 阶段，旧标签先留着，
    /// 新结果回来直接替换，不闪、不转圈。
    ///
    /// tier：调用方（WatchlistView/ResultDetailView）按 `store.tier` 传入，决定自选上限
    /// （见 fetchAndApply）——自选本身现在所有档位都能用，只是上限不同（未订阅 1 / 基础版
    /// 10 / 高级版不限），不再是高级版专属。
    func onAppear(tier: SubscriptionTier) async {
        if items.isEmpty {
            await refresh(tier: tier)
            return
        }
        try? await fetchAndApply(tier: tier)
        if tier == .premium { await loadPhases() } else { phases = [:] }
    }

    func refresh(tier: SubscriptionTier) async {
        isLoading = true
        defer { isLoading = false }
        do {
            try await fetchAndApply(tier: tier)
        } catch {
            errorMessage = (error as? APIError)?.message ?? "加载自选失败"
            return
        }
        if tier == .premium { await loadPhases() } else { phases = [:] }
    }

    /// 拉阶段标签：单独一次请求，比拉列表慢（要跑缠论分析）。失败隔 2 秒重试一次，
    /// 仍失败则保留旧标签——阶段标签是锦上添花，不该因此把整个自选列表判定为加载失败。
    /// 进行中不重复发起（快速来回切 tab 时）。
    private func loadPhases() async {
        guard !isLoadingPhases else { return }
        isLoadingPhases = true
        defer { isLoadingPhases = false }
        for attempt in 0..<2 {
            if let resp = try? await WatchlistService.phases() {
                phases = resp.phases
                return
            }
            guard attempt == 0, !Task.isCancelled else { return }
            try? await Task.sleep(for: .seconds(2))
        }
    }

    /// 只用来判断分析结果页当前标的的星标状态，不需要展示 loading，失败静默即可
    /// （星标按钮退回「未收藏」态，用户点一下会再次尝试）。
    func refreshSilently(tier: SubscriptionTier) async {
        try? await fetchAndApply(tier: tier)
    }

    private func fetchAndApply(tier: SubscriptionTier) async throws {
        let resp = try await WatchlistService.list(tier: tier.apiValue)
        items = resp.items
        maxItems = resp.maxItems
        memberships = Set(items.map { Self.key(marketRaw: $0.market, symbol: $0.symbol) })
    }

    /// 星标切换：乐观更新 UI，失败回退并重新拉取真实状态。
    ///
    /// 加入前先在端上按 `maxItems` 短路一次，省一次注定失败的网络往返；
    /// 服务端仍会在 `WatchlistService.add` 里按 tier 做最终校验（见 `catch`），保证
    /// 并发加入（如两台设备同时各加一支）不会让总数超过该档上限。
    func toggle(market: StockMarket, symbol: String, name: String, tier: SubscriptionTier) async {
        let key = Self.key(market: market, symbol: symbol)
        if memberships.contains(key) {
            memberships.remove(key)
            items.removeAll { $0.market == market.rawValue && $0.symbol == symbol }
            do {
                try await WatchlistService.remove(market: market, symbol: symbol)
                NotificationCenter.default.post(name: .watchlistDidChange, object: nil)
            } catch {
                errorMessage = (error as? APIError)?.message ?? "移出自选失败"
                await refresh(tier: tier)
            }
        } else {
            if isFull, let maxItems {
                errorMessage = L("自选最多添加 %lld 支标的，请先移出几支再试", maxItems)
                return
            }
            memberships.insert(key)
            do {
                let item = try await WatchlistService.add(market: market, symbol: symbol, name: name, tier: tier.apiValue)
                items.insert(item, at: 0)
                NotificationCenter.default.post(name: .watchlistDidChange, object: nil)
            } catch {
                memberships.remove(key)
                errorMessage = (error as? APIError)?.message ?? "加入自选失败"
            }
        }
    }

    func remove(_ item: WatchlistItem, tier: SubscriptionTier) async {
        guard let market = StockMarket(rawValue: item.market) else { return }
        memberships.remove(Self.key(market: market, symbol: item.symbol))
        items.removeAll { $0.id == item.id }
        do {
            try await WatchlistService.remove(market: market, symbol: item.symbol)
            NotificationCenter.default.post(name: .watchlistDidChange, object: nil)
        } catch {
            errorMessage = (error as? APIError)?.message ?? "移出自选失败"
            await refresh(tier: tier)
        }
    }

    private static func key(market: StockMarket, symbol: String) -> String {
        "\(market.rawValue):\(symbol)"
    }

    private static func key(marketRaw: String, symbol: String) -> String {
        "\(marketRaw):\(symbol)"
    }
}
