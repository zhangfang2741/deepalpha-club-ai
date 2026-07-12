import Foundation

/// 免费用户每日分析额度追踪（端上，UserDefaults 按自然日归零）。
///
/// 计量单位为「不同标的」：同一支股票当天重复分析（切周期、改日期）不重复扣费，
/// 只有当天分析第 N+1 支新标的时才被拦截。
///
/// 说明：端上计数便于快速实现，但可被重装/改时间绕过；
/// 如需严格限制，可将额度改由后端按用户维度校验（后续加固）。
@MainActor
final class UsageTracker: ObservableObject {
    /// 今日已分析过的标的集合。
    @Published private(set) var symbolsToday: Set<String> = []

    private let defaults = UserDefaults.standard
    private let symbolsKey = "free_analysis_symbols"
    private let dateKey = "free_analysis_date"

    var dailyQuota: Int { AppConfig.freeDailyQuota }
    var usedToday: Int { symbolsToday.count }
    var remaining: Int { max(0, dailyQuota - usedToday) }

    init() { rolloverIfNeeded() }

    private var todayString: String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f.string(from: Date())
    }

    private func normalize(_ symbol: String) -> String {
        symbol.trimmingCharacters(in: .whitespaces).uppercased()
    }

    /// 跨天则重置。
    private func rolloverIfNeeded() {
        if defaults.string(forKey: dateKey) != todayString {
            defaults.set(todayString, forKey: dateKey)
            defaults.removeObject(forKey: symbolsKey)
            symbolsToday = []
        } else {
            symbolsToday = Set(defaults.stringArray(forKey: symbolsKey) ?? [])
        }
    }

    /// 该标的是否可免费分析：已分析过（不重复扣）或今日额度未用尽。
    func canUseFree(symbol: String) -> Bool {
        rolloverIfNeeded()
        let s = normalize(symbol)
        if s.isEmpty { return true }  // 空输入交给上层校验，不占额度
        return symbolsToday.contains(s) || symbolsToday.count < dailyQuota
    }

    /// 记录一次对某标的的分析（同标的重复调用无副作用）。
    func recordUse(symbol: String) {
        rolloverIfNeeded()
        let s = normalize(symbol)
        guard !s.isEmpty, !symbolsToday.contains(s) else { return }
        symbolsToday.insert(s)
        defaults.set(Array(symbolsToday), forKey: symbolsKey)
    }
}
