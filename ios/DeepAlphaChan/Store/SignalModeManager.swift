import Foundation

/// 买卖点口径的无状态入口：网络层（非 MainActor）从这里读，跟 `Localized` 同一个做法。
///
/// App 统一使用严格口径（缠论原文定义：买卖点落在已走完的笔上），雷达、详情页、次级别都带同一个
/// `mode`，从雷达点进详情两边的买卖点一致。设置页不提供切换（忽略 UserDefaults 里残留的旧选择）。
/// 后端默认口径仍是宽松（线上旧版 App 在用），两套都每天预热（scheduler._modes）。
enum SignalMode {
    /// App 使用的口径。
    static let defaultKey = "strict"

    /// 当前生效的口径键（每个接口请求都带上 `mode`）。
    static func current() -> String { defaultKey }
}
