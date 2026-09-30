import Foundation

/// 详情页「量化研究」「分析师评级」两个分段的数据：切到对应分段才加载，
/// 按「市场 + 代码 + 语言」缓存，来回切换不重复请求。
@MainActor
final class QuantResearchViewModel: ObservableObject {
    enum LoadState<T> {
        case idle, loading, loaded(T), failed(String)
    }

    @Published private(set) var research: LoadState<QuantResearch> = .idle
    @Published private(set) var analyst: LoadState<AnalystOverview> = .idle
    @Published private(set) var methodology: QuantMethodology?

    private var researchKey: String?
    private var analystKey: String?

    private static func key(_ market: StockMarket, _ symbol: String) -> String {
        "\(market.rawValue):\(symbol.uppercased()):\(Localized.language().rawValue)"
    }

    func loadResearch(market: StockMarket, symbol: String, force: Bool = false) async {
        let key = Self.key(market, symbol)
        if !force, researchKey == key, case .loaded = research { return }
        researchKey = key
        research = .loading
        do {
            let r = try await QuantResearchService.research(market: market, symbol: symbol)
            guard researchKey == key else { return }
            research = .loaded(r)
        } catch {
            guard researchKey == key else { return }
            research = .failed((error as? APIError)?.message ?? error.localizedDescription)
        }
    }

    func loadAnalyst(market: StockMarket, symbol: String, force: Bool = false) async {
        let key = Self.key(market, symbol)
        if !force, analystKey == key, case .loaded = analyst { return }
        analystKey = key
        analyst = .loading
        do {
            let r = try await QuantResearchService.analystOverview(market: market, symbol: symbol)
            guard analystKey == key else { return }
            analyst = .loaded(r)
        } catch {
            guard analystKey == key else { return }
            analyst = .failed((error as? APIError)?.message ?? error.localizedDescription)
        }
    }

    func loadMethodology() async {
        if methodology != nil { return }
        methodology = try? await QuantResearchService.methodology()
    }
}
