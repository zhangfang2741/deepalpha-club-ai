// App/Localization.swift
import Foundation
import SwiftUI

// MARK: - 如何新增一门语言（扩展指南）
//
// 本地化被设计成「加一门语言只改一处枚举 + 加一个 .lproj」：
//   1. 在 `AppLanguage` 里加一个 case（rawValue = 对应 .lproj 目录名，如 "ja"）。
//   2. 在 `nativeName` 里补上它的母语名字（如 "日本語"）。
//   3. 在 Resources 下新建 `<code>.lproj/Localizable.strings` 与 `InfoPlist.strings`，
//      key 沿用中文原文（缺翻译会自动退回中文，不会露出 raw key）。
//   4. 如需让某些地区默认用这门语言，在 `regionLanguageMap` 里加地区→语言映射。
// 设置页的语言选择器、环境 locale 注入都会自动带上新语言，无需再改 UI。

/// App 支持的界面语言。rawValue 必须与 `Resources/<rawValue>.lproj` 目录名一致。
enum AppLanguage: String, CaseIterable, Identifiable, Sendable {
    case chinese = "zh-Hans"
    case english = "en"

    var id: String { rawValue }
    var localeIdentifier: String { rawValue }

    /// 用该语言自己的文字书写的名字（母语原则），在任何界面语言下都原样显示。
    var nativeName: String {
        switch self {
        case .chinese: return "中文"
        case .english: return "English"
        }
    }
}

/// 无持久化选择时的兜底语言（新地区默认走这个）。
private let fallbackLanguage: AppLanguage = .english

/// 地区 → 默认语言的映射。只列「非兜底」的地区即可。
/// 需求：中国大陆用中文，其它地区用英文——所以这里只放 CN。
private let regionLanguageMap: [String: AppLanguage] = [
    "CN": .chinese,
]

/// 语言解析与字符串查表的无状态入口。
///
/// 网络层、语音识别等非 `@MainActor` 代码也要取文案，从这里读 `UserDefaults`
/// （线程安全）避免跨 actor 访问 `@Published` 状态；UI 的实时刷新交给
/// `LocalizationManager`。两者共用同一套解析逻辑。
enum Localized {
    static let preferenceKey = "app_language_preference"
    /// 「跟随系统」在 UserDefaults 里的存储值（区别于具体语言的 rawValue）。
    static let systemValue = "system"

    /// 按地区自动决定语言。命中 `regionLanguageMap` 用映射，否则用兜底语言。
    static func regionDefault() -> AppLanguage {
        let region = Locale.current.region?.identifier ?? ""
        return regionLanguageMap[region] ?? fallbackLanguage
    }

    /// 读取持久化的偏好。返回 nil 表示「跟随系统」。
    static func preference() -> AppLanguage? {
        guard let raw = UserDefaults.standard.string(forKey: preferenceKey),
              raw != systemValue else { return nil }
        return AppLanguage(rawValue: raw)
    }

    /// 当前生效的具体语言（把「跟随系统」解析成某门语言）。
    static func language() -> AppLanguage {
        preference() ?? regionDefault()
    }

    // 每次查表都新建 Bundle 会有开销（列表滚动时 L() 调用非常频繁），
    // 按语言缓存已加载的 .lproj bundle。
    private static var bundleCache: [String: Bundle] = [:]
    private static let cacheLock = NSLock()

    private static func bundle(for lang: AppLanguage) -> Bundle {
        cacheLock.lock(); defer { cacheLock.unlock() }
        if let cached = bundleCache[lang.rawValue] { return cached }
        let resolved: Bundle
        if let path = Bundle.main.path(forResource: lang.rawValue, ofType: "lproj"),
           let b = Bundle(path: path) {
            resolved = b
        } else {
            resolved = .main
        }
        bundleCache[lang.rawValue] = resolved
        return resolved
    }

    /// 查表；查不到返回 key 本身。所有 key 都是中文原文，缺翻译会自然退回中文，
    /// 绝不会给用户看到 raw key。
    static func string(_ key: String) -> String {
        bundle(for: language()).localizedString(forKey: key, value: key, table: nil)
    }

    /// 带格式参数的查表（key 里用 %@ / %lld 等占位符）。
    static func string(_ key: String, _ args: [CVarArg]) -> String {
        let lang = language()
        let format = bundle(for: lang).localizedString(forKey: key, value: key, table: nil)
        return String(format: format, locale: Locale(identifier: lang.localeIdentifier), arguments: args)
    }
}

/// 全局取文案快捷函数。所有对用户可见的中文字面量都应走它，
/// 这样界面在任何上下文（Text / String 属性 / 拼接）下都不会漏出中文。
func L(_ key: String) -> String { Localized.string(key) }
func L(_ key: String, _ args: CVarArg...) -> String { Localized.string(key, args) }

/// 驱动界面在切换语言时实时刷新的可观察状态。
/// 只保存偏好（nil = 跟随系统），具体解析交给 `Localized`。
@MainActor
final class LocalizationManager: ObservableObject {
    static let shared = LocalizationManager()

    /// nil 表示「跟随系统/地区自动」。
    @Published var preference: AppLanguage? {
        didSet {
            UserDefaults.standard.set(preference?.rawValue ?? Localized.systemValue,
                                      forKey: Localized.preferenceKey)
        }
    }

    private init() {
        preference = Localized.preference()
    }

    /// 当前生效语言。
    var language: AppLanguage { preference ?? Localized.regionDefault() }

    /// 注入 SwiftUI 环境，用于日期/数字等系统格式化按语言走。
    var locale: Locale { Locale(identifier: language.localeIdentifier) }
}
