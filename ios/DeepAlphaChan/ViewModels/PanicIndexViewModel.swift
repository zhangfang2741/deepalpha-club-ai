import Foundation

/// 三地恐慌指数：一次性并行拉美股/A股/港股，三个小卡片同时展示，互不依赖「市场」页
/// 当前选中的市场——选中哪个市场只影响下面的信号雷达内容，恐慌指数三张卡永远都在。
@MainActor
final class PanicIndexViewModel: ObservableObject {
    @Published private(set) var responses: [StockMarket: PanicIndexResponse] = [:]
    /// 拉取失败的市场：卡片上给个可重试的错误态，而不是转圈转到天荒地老。
    @Published private(set) var failedMarkets: Set<StockMarket> = []
    @Published private(set) var isLoading = false

    func onAppear() {
        guard responses.isEmpty && !isLoading else { return }
        Task { await load() }
    }

    func retry(_ market: StockMarket) {
        failedMarkets.remove(market)
        Task { await loadOne(market) }
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        await withTaskGroup(of: Void.self) { group in
            for market in StockMarket.allCases {
                group.addTask { await self.loadOne(market) }
            }
            await group.waitForAll()
        }
    }

    private func loadOne(_ market: StockMarket) async {
        do {
            responses[market] = try await PanicIndexService.fetch(market: market.rawValue)
            failedMarkets.remove(market)
        } catch {
            failedMarkets.insert(market)
        }
    }
}
