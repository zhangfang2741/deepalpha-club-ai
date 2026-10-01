import Foundation

/// 雷达页顶部「宏观 / 行业」两格的数据：按市场各拉一次摘要（GET /macro/{market}/overview），
/// 切市场时切到对应那份；情绪格仍由 PanicIndexViewModel 负责。
/// 弹层的完整数据（宏观详情、行业列表）由弹层自己按需拉，不放这里。
@MainActor
final class MarketOverviewViewModel: ObservableObject {
    @Published private(set) var overviews: [StockMarket: MarketOverview] = [:]
    @Published private(set) var failedMarkets: Set<StockMarket> = []
    private var loading: Set<StockMarket> = []
    /// 上次成功加载的时刻：摘要每天只变一次（收盘后 regime 重算），回到页面超过 30 分钟才重拉。
    private var loadedAt: [StockMarket: Date] = [:]
    private let refreshInterval: TimeInterval = 30 * 60

    func load(_ market: StockMarket) {
        if let at = loadedAt[market], Date().timeIntervalSince(at) < refreshInterval { return }
        guard !loading.contains(market) else { return }
        loading.insert(market)
        Task {
            defer { loading.remove(market) }
            do {
                overviews[market] = try await MarketOverviewService.overview(market: market)
                loadedAt[market] = Date()
                failedMarkets.remove(market)
            } catch {
                if overviews[market] == nil { failedMarkets.insert(market) }
            }
        }
    }

    func retry(_ market: StockMarket) {
        failedMarkets.remove(market)
        loadedAt[market] = nil
        load(market)
    }
}
