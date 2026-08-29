import Foundation

/// 最近分析过的标的（端上，UserDefaults 持久化，跨天保留）。
///
/// 和 UsageTracker 里的 `symbolsToday` 是两回事：那个是当日计费用的无序集合、
/// 隔天清零；这个是给用户当快捷入口的**有序**历史，最新在前、跨天保留。
///
/// 存的是「市场 + 代码」而不是光一个代码：0700 在港股、600519 在 A 股，
/// 只恢复代码不恢复市场，点一下就会拿美股去查一个数字代码。
@MainActor
final class RecentSymbols: ObservableObject {
    struct Entry: Identifiable, Equatable {
        let market: StockMarket
        let symbol: String

        var id: String { "\(market.rawValue):\(symbol)" }

        /// 美股是字母代码，一眼能认；A 股/港股都是数字，不标市场会混。
        var display: String {
            guard let tag = market.shortTag else { return symbol }
            return "\(tag) \(symbol)"
        }
    }

    /// 最新在前。上限 6 条——查询页那一行横向排得下的量，再多就要滚动了。
    @Published private(set) var entries: [Entry] = []

    private let defaults = UserDefaults.standard
    private let key = "recent_analyzed_symbols"
    private let limit = 6

    init() {
        entries = (defaults.stringArray(forKey: key) ?? []).compactMap(Self.decode)
    }

    /// 记录一次分析。已存在的条目提到最前，不产生重复。
    func record(market: StockMarket, symbol: String) {
        let clean = symbol.trimmingCharacters(in: .whitespaces).uppercased()
        guard !clean.isEmpty else { return }
        let entry = Entry(market: market, symbol: clean)
        entries.removeAll { $0 == entry }
        entries.insert(entry, at: 0)
        if entries.count > limit { entries.removeLast(entries.count - limit) }
        defaults.set(entries.map(\.id), forKey: key)
    }

    /// `"us:AAPL"` → Entry。市场段无法识别时丢弃该条（旧版本写入的脏数据）。
    private static func decode(_ raw: String) -> Entry? {
        let parts = raw.split(separator: ":", maxSplits: 1)
        guard parts.count == 2, let market = StockMarket(rawValue: String(parts[0])) else {
            return nil
        }
        return Entry(market: market, symbol: String(parts[1]))
    }
}
