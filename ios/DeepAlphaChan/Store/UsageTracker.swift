import Foundation

/// 免费用户每日分析额度追踪（端上，UserDefaults 按自然日归零）。
///
/// 说明：端上计数便于快速实现，但可被重装/改时间绕过；
/// 如需严格限制，可将额度改由后端按用户维度校验（后续加固）。
@MainActor
final class UsageTracker: ObservableObject {
    @Published private(set) var usedToday: Int = 0

    private let defaults = UserDefaults.standard
    private let countKey = "free_analysis_count"
    private let dateKey = "free_analysis_date"

    var dailyQuota: Int { AppConfig.freeDailyQuota }
    var remaining: Int { max(0, dailyQuota - usedToday) }

    init() { rolloverIfNeeded() }

    private var todayString: String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f.string(from: Date())
    }

    /// 跨天则重置计数。
    private func rolloverIfNeeded() {
        if defaults.string(forKey: dateKey) != todayString {
            defaults.set(todayString, forKey: dateKey)
            defaults.set(0, forKey: countKey)
        }
        usedToday = defaults.integer(forKey: countKey)
    }

    /// 免费额度是否还有剩余。
    func canUseFree() -> Bool {
        rolloverIfNeeded()
        return usedToday < dailyQuota
    }

    /// 记一次使用。
    func recordUse() {
        rolloverIfNeeded()
        usedToday += 1
        defaults.set(usedToday, forKey: countKey)
    }
}
