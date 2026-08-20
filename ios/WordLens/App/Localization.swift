// App/Localization.swift
import Foundation
import SwiftUI

/// App 实际使用的界面语言（只有中文 / 英文两种）。
///
/// 和 `LanguagePreference` 区分开：偏好里还有「跟随系统」这个选项，最终会被
/// `LocalizationManager` 解析成这里的某一种具体语言。
enum AppLanguage: String, CaseIterable, Identifiable {
    case chinese = "zh-Hans"
    case english = "en"

    var id: String { rawValue }

    /// SwiftUI `.environment(\.locale, …)` 和 `.lproj` 目录名都用这个标识符。
    var localeIdentifier: String { rawValue }

    /// 在设置页里给这门语言起的名字，用它自己的文字写（母语原则）。
    var nativeName: String {
        switch self {
        case .chinese: return "中文"
        case .english: return "English"
        }
    }
}

/// 用户在设置里选的语言偏好。`system` 表示「跟随系统/地区自动判断」。
enum LanguagePreference: String, CaseIterable, Identifiable {
    case system
    case chinese = "zh-Hans"
    case english = "en"

    var id: String { rawValue }
}

/// 语言解析与字符串查表的无状态入口。
///
/// 之所以不直接用 `LocalizationManager.shared`：网络层、语音识别等非 `@MainActor`
/// 的代码也要取本地化文案，从这里读 `UserDefaults`（线程安全）避免跨 actor 访问
/// `@Published` 状态。UI 的实时刷新交给 `LocalizationManager`。
enum Localized {
    static let preferenceKey = "app_language_preference"

    /// 没有任何持久化选择时，按地区自动决定：中国大陆 → 中文，其它 → 英文。
    static func regionDefault() -> AppLanguage {
        let region = Locale.current.region?.identifier ?? ""
        return region == "CN" ? .chinese : .english
    }

    static func preference() -> LanguagePreference {
        let raw = UserDefaults.standard.string(forKey: preferenceKey)
        return LanguagePreference(rawValue: raw ?? "") ?? .system
    }

    /// 当前生效的具体语言（把「跟随系统」解析成中文或英文）。
    static func language() -> AppLanguage {
        switch preference() {
        case .system: return regionDefault()
        case .chinese: return .chinese
        case .english: return .english
        }
    }

    /// 当前语言对应的 `.lproj` bundle；找不到就退回主 bundle（会走 key 兜底）。
    static func bundle() -> Bundle {
        let lang = language()
        guard let path = Bundle.main.path(forResource: lang.localeIdentifier, ofType: "lproj"),
              let bundle = Bundle(path: path)
        else { return .main }
        return bundle
    }

    /// 查表；查不到时返回 key 本身。因为所有 key 都是中文原文，缺翻译时会自然
    /// 退回中文，绝不会给用户看到一串 raw key。
    static func string(_ key: String) -> String {
        bundle().localizedString(forKey: key, value: key, table: nil)
    }

    /// 带格式参数的查表。key 里用 `%@` / `%d` 等占位符，缺翻译时退回中文 key
    /// 再做 `String(format:)`，参数照样能填进去。
    static func string(_ key: String, _ args: [CVarArg]) -> String {
        let format = bundle().localizedString(forKey: key, value: key, table: nil)
        return String(format: format, locale: Locale(identifier: language().localeIdentifier), arguments: args)
    }
}

/// 命令式代码（ViewModel / Service / 模型 label）取文案用的全局快捷函数。
///
/// SwiftUI 的 `Text("中文")` 会自动走 `.environment(\.locale)` + `Localizable.strings`，
/// 不需要改；但存进 `String` 属性的文案（如报错信息、模型 `label`）不吃环境 locale，
/// 必须显式用 `L(...)`。
func L(_ key: String) -> String { Localized.string(key) }
func L(_ key: String, _ args: CVarArg...) -> String { Localized.string(key, args) }

/// 驱动界面在切换语言时实时刷新的可观察状态。
///
/// 只保存「偏好」；具体解析成哪门语言交给 `Localized`，两边共用同一套逻辑。
@MainActor
final class LocalizationManager: ObservableObject {
    static let shared = LocalizationManager()

    @Published var preference: LanguagePreference {
        didSet {
            UserDefaults.standard.set(preference.rawValue, forKey: Localized.preferenceKey)
        }
    }

    private init() {
        preference = Localized.preference()
    }

    /// 当前生效语言。切「跟随系统」时也会随地区解析。
    var language: AppLanguage {
        switch preference {
        case .system: return Localized.regionDefault()
        case .chinese: return .chinese
        case .english: return .english
        }
    }

    /// 注入到 SwiftUI 环境，让所有 `Text` 字面量按此语言查 `Localizable.strings`。
    var locale: Locale { Locale(identifier: language.localeIdentifier) }
}
