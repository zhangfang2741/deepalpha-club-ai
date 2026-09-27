import Foundation

/// 买卖点口径的无状态入口：网络层（非 MainActor）从这里读，跟 `Localized` 同一个做法。
///
/// App 统一使用宽松口径，设置页不再提供切换；以前选过「严格」的用户也回到宽松
/// （忽略 UserDefaults 里残留的旧选择）。后端仍支持 strict，需要时再开放。
enum SignalMode {
    /// 后端默认口径。
    static let defaultKey = "loose"

    /// 当前生效的口径键（每个接口请求都带上 `mode`）。
    static func current() -> String { defaultKey }
}
