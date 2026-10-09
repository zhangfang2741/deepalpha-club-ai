import Foundation

/// 买卖点口径的无状态入口：网络层（非 MainActor）从这里读，跟 `Localized` 同一个做法。
///
/// 三套口径（后端 app/services/chan/signal_policy.py，定时任务三套都预热）：
/// strict 严格（缠论原文）/ medium 中等（默认，严格 + 盘整背驰）/ loose 宽松（最后一笔未走完也先标出）。
/// 用户在「我的 → 买卖点口径」自己切换，选择存在 UserDefaults（改了会发 `didChange` 通知，雷达据此重载）；雷达、详情页、次级别都带同一个 `mode`，
/// 从雷达点进详情两边的买卖点一致。
enum SignalMode {
    static let storageKey = "signal_mode"
    /// 可选口径，按「从严到宽」排列（切换面板的顺序）。
    static let all = ["strict", "medium", "loose"]
    static let defaultKey = "medium"
    static let didChange = Notification.Name("signal_mode_did_change")

    /// 当前生效的口径键（每个接口请求都带上 `mode`）。存的值不认识（旧版本残留）就用默认。
    static func current() -> String {
        let saved = UserDefaults.standard.string(forKey: storageKey) ?? ""
        return all.contains(saved) ? saved : defaultKey
    }

    static func set(_ key: String) {
        guard all.contains(key) else { return }
        guard key != current() else { return }
        UserDefaults.standard.set(key, forKey: storageKey)
        NotificationCenter.default.post(name: didChange, object: nil)
    }

    /// 界面上的口径名。
    static func title(_ key: String) -> String {
        switch key {
        case "strict": return L("严格")
        case "loose": return L("宽松")
        default: return L("中等")
        }
    }
}
