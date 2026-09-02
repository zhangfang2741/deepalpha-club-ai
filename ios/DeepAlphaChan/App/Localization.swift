import Foundation
import SwiftUI

// MARK: - 如何新增一门语言（扩展指南）
//
// 本地化被设计成「加一门语言只改一处枚举 + 加一个 .lproj」：
//   1. 在 `AppLanguage` 里加一个 case（rawValue = 对应 .lproj 目录名，如 "ja"）。
//   2. 在 `nativeName` 里补上它的母语名字（如 "日本語"）。
//   3. 在 Resources 下新建 `<code>.lproj/Localizable.strings`（key 沿用中文原文，
//      缺翻译会自动退回中文，不会露出 raw key）。
//   4. 可选：若某些地区要无视系统语言、一律用这门语言，在 `regionLanguageMap` 加映射。
//      不加也没关系——系统语言是这门语言的用户会被 `systemLanguage()` 自动匹配上。
// 设置页的语言选择器、环境 locale 注入都会自动带上新语言，无需再改 UI。
//
// 实现与鹦鹉背单词（WordLens）保持一致，便于两 App 共同维护。

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

/// 地区没命中、系统语言也不支持时的最终兜底。
private let fallbackLanguage: AppLanguage = .english

/// 地区 → 强制语言的映射。命中的地区不再看系统语言，直接用映射值。
/// 只列需要「按地区一刀切」的地区，其余地区交给系统语言判断。
private let regionLanguageMap: [String: AppLanguage] = [
    "CN": .chinese,
]

/// 语言解析与字符串查表的无状态入口。
///
/// 网络层等非 `@MainActor` 代码也要取文案，从这里读 `UserDefaults`（线程安全）
/// 避免跨 actor 访问 `@Published` 状态；UI 的实时刷新交给 `LocalizationManager`。
enum Localized {
    static let preferenceKey = "app_language_preference"
    /// 「跟随系统」在 UserDefaults 里的存储值（区别于具体语言的 rawValue）。
    static let systemValue = "system"

    /// 「跟随系统」时的自动语言，三级判断：
    ///   1. 地区命中 `regionLanguageMap`（中国大陆）→ 直接用映射值；
    ///   2. 否则看系统偏好语言，取第一门 App 支持的；
    ///   3. 都不中（如泰语系统 + 泰国地区）→ `fallbackLanguage`。
    ///
    /// 第 2 步是关键：出国旅居把地区改成 TH/SG 的中文用户，系统语言仍是中文，
    /// 只按地区判断会把他们甩到英文界面。
    static func autoDefault() -> AppLanguage {
        let region = Locale.current.region?.identifier ?? ""
        if let mapped = regionLanguageMap[region] { return mapped }
        return systemLanguage() ?? fallbackLanguage
    }

    /// 从系统偏好语言列表里找第一门 App 支持的语言，找不到返回 nil。
    ///
    /// 只比语言代码、忽略地区与字形后缀：`zh-Hant-TW`、`zh-Hans-SG` 都会归到
    /// `zh-Hans`——目前没有繁体资源，给繁体用户简体也比甩英文近。
    /// 遍历 `allCases` 而非写死判断，新增语言时这里自动生效。
    private static func systemLanguage() -> AppLanguage? {
        let supported = AppLanguage.allCases.map {
            ($0, Locale(identifier: $0.rawValue).language.languageCode?.identifier)
        }
        for identifier in Locale.preferredLanguages {
            guard let code = Locale(identifier: identifier).language.languageCode?.identifier
            else { continue }
            if let match = supported.first(where: { $0.1 == code })?.0 { return match }
        }
        return nil
    }

    /// 读取持久化的偏好。返回 nil 表示「跟随系统」。
    static func preference() -> AppLanguage? {
        guard let raw = UserDefaults.standard.string(forKey: preferenceKey),
              raw != systemValue else { return nil }
        return AppLanguage(rawValue: raw)
    }

    /// 当前生效的具体语言（把「跟随系统」解析成某门语言）。
    static func language() -> AppLanguage {
        preference() ?? autoDefault()
    }

    // 每次查表都新建 Bundle 会有开销，按语言缓存已加载的 .lproj bundle。
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

    /// 当前语言对应的 .lproj 资源包（供加载 lessons.json 等本地化资源用）。
    static func resourceBundle() -> Bundle {
        bundle(for: language())
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

/// 全局取文案快捷函数。所有对用户可见的中文字面量都应走它。
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
    var language: AppLanguage { preference ?? Localized.autoDefault() }

    /// 注入 SwiftUI 环境，用于日期/数字等系统格式化按语言走。
    var locale: Locale { Locale(identifier: language.localeIdentifier) }
}
