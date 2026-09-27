import Foundation

/// 买卖点模式（宽松 / 严格 / …）的一个选项，来自 GET /chan/signal-modes。
struct SignalModeOption: Decodable, Identifiable, Hashable {
    let key: String
    let label: String
    let description: String
    let isDefault: Bool

    var id: String { key }

    enum CodingKeys: String, CodingKey {
        case key, label, description
        case isDefault = "is_default"
    }
}

private struct SignalModesResponse: Decodable {
    let `default`: String
    let modes: [SignalModeOption]
}

/// 买卖点模式的无状态入口：网络层（非 MainActor）从这里读当前选择，跟 `Localized` 同一个做法。
enum SignalMode {
    static let preferenceKey = "signal_mode_preference"
    /// 后端默认口径；没选过、或选过的口径已下线时用它。
    static let defaultKey = "loose"

    /// 当前生效的口径键（每个接口请求都带上 `mode`）。
    static func current() -> String {
        UserDefaults.standard.string(forKey: preferenceKey) ?? defaultKey
    }
}

/// 驱动设置页与各页面在切换模式时刷新的可观察状态。
///
/// 可选项以服务端为准（以后加「中等」等模式不用发版）；拉取前 / 失败时用本地内置的两项兜底。
@MainActor
final class SignalModeManager: ObservableObject {
    static let shared = SignalModeManager()

    @Published var mode: String {
        didSet {
            guard mode != oldValue else { return }
            UserDefaults.standard.set(mode, forKey: SignalMode.preferenceKey)
        }
    }

    @Published private(set) var options: [SignalModeOption] = SignalModeManager.builtinOptions

    private init() {
        mode = SignalMode.current()
    }

    static var builtinOptions: [SignalModeOption] {
        [
            SignalModeOption(key: "loose", label: L("宽松"),
                             description: L("信号更多、出得更早，最后一笔还在走时也先标出（未确认）"),
                             isDefault: true),
            SignalModeOption(key: "strict", label: L("严格"),
                             description: L("严格按缠论原文定义，只认已走完的笔"),
                             isDefault: false),
        ]
    }

    var currentOption: SignalModeOption? { options.first { $0.key == mode } }

    /// 从服务端拉可选项（按界面语言）。当前选择已不在列表里时回退服务端默认。
    func loadOptions() async {
        let lang = Localized.language() == .english ? "en" : "zh"
        guard let resp: SignalModesResponse = try? await APIClient.shared.get(
            "/chan/signal-modes", query: ["lang": lang]), !resp.modes.isEmpty else { return }
        options = resp.modes
        if !resp.modes.contains(where: { $0.key == mode }) { mode = resp.default }
    }
}
