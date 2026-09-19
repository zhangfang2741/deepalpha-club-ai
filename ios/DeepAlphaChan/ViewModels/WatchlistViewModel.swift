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

    private var memberships: Set<String> = []

    func isStarred(market: StockMarket, symbol: String) -> Bool {
        memberships.contains(Self.key(market: market, symbol: symbol))
    }

    /// 已有数据时不重复拉取；下拉刷新走 `refresh()`。
    func onAppear() async {
        guard items.isEmpty else { return }
        await refresh()
    }

    func refresh() async {
        isLoading = true
        defer { isLoading = false }
        do {
            try await fetchAndApply()
        } catch {
            errorMessage = (error as? APIError)?.message ?? "加载自选失败"
        }
    }

    /// 只用来判断分析结果页当前标的的星标状态，不需要展示 loading，失败静默即可
    /// （星标按钮退回「未收藏」态，用户点一下会再次尝试）。
    func refreshSilently() async {
        try? await fetchAndApply()
    }

    private func fetchAndApply() async throws {
        let resp = try await WatchlistService.list()
        items = resp.items
        memberships = Set(items.map { Self.key(marketRaw: $0.market, symbol: $0.symbol) })
    }

    /// 星标切换：乐观更新 UI，失败回退并重新拉取真实状态。
    func toggle(market: StockMarket, symbol: String, name: String) async {
        let key = Self.key(market: market, symbol: symbol)
        if memberships.contains(key) {
            memberships.remove(key)
            items.removeAll { $0.market == market.rawValue && $0.symbol == symbol }
            do {
                try await WatchlistService.remove(market: market, symbol: symbol)
                NotificationCenter.default.post(name: .watchlistDidChange, object: nil)
            } catch {
                errorMessage = (error as? APIError)?.message ?? "移出自选失败"
                await refresh()
            }
        } else {
            memberships.insert(key)
            do {
                let item = try await WatchlistService.add(market: market, symbol: symbol, name: name)
                items.insert(item, at: 0)
                NotificationCenter.default.post(name: .watchlistDidChange, object: nil)
            } catch {
                memberships.remove(key)
                errorMessage = (error as? APIError)?.message ?? "加入自选失败"
            }
        }
    }

    func remove(_ item: WatchlistItem) async {
        guard let market = StockMarket(rawValue: item.market) else { return }
        memberships.remove(Self.key(market: market, symbol: item.symbol))
        items.removeAll { $0.id == item.id }
        do {
            try await WatchlistService.remove(market: market, symbol: item.symbol)
            NotificationCenter.default.post(name: .watchlistDidChange, object: nil)
        } catch {
            errorMessage = (error as? APIError)?.message ?? "移出自选失败"
            await refresh()
        }
    }

    private static func key(market: StockMarket, symbol: String) -> String {
        "\(market.rawValue):\(symbol)"
    }

    private static func key(marketRaw: String, symbol: String) -> String {
        "\(marketRaw):\(symbol)"
    }
}
