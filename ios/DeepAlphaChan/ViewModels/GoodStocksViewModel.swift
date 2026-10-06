import Foundation

/// 「好股票」名单的数据：当前（市场, 指数）里综合等级最高的若干只（含近 30 天券商评级净上调 / 下调，仅美股）。
/// 门槛由后端定（雷达响应的 qualityThreshold），这里只负责拉名单；每只股票有没有买卖点由雷达自己的信号判断。
@MainActor
final class GoodStocksViewModel: ObservableObject {
    @Published private(set) var response: FundamentalTopResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var failed = false
    /// 已加载数据对应的 (市场, 指数)；与当前请求不同 = 刚切了范围，旧名单不展示。
    private var loadedKey = ""
    private var requestedKey = ""

    /// 13 档字母等级，A+ 最高、F 最低（与后端 GRADE_ORDER 一致）。
    static let gradeOrder = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]

    var items: [FundamentalItem] { loadedKey == requestedKey ? (response?.items ?? []) : [] }

    /// 只留不低于 threshold（如 "B+"）的；threshold 为空时不筛。
    func items(atLeast threshold: String?) -> [FundamentalItem] {
        guard let threshold, let limit = Self.gradeOrder.firstIndex(of: threshold) else { return items }
        return items.filter { (Self.gradeOrder.firstIndex(of: $0.grade) ?? Int.max) <= limit }
    }

    func load(market: String, universe: String?) async {
        let key = "\(market)|\(universe ?? "")"
        requestedKey = key
        if key == loadedKey, response != nil { return }
        isLoading = true
        failed = false
        defer { if requestedKey == key { isLoading = false } }
        do {
            let resp = try await SignalRadarService.fundamentalTop(market: market, universe: universe)
            guard requestedKey == key else { return }
            loadedKey = key
            response = resp
        } catch {
            if Task.isCancelled || requestedKey != key { return }
            failed = true
        }
    }
}
