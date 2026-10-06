import Foundation

/// 名词小词典的一个词条：给没学过金融的人一句大白话、一个例子、一句「它不代表什么」。
///
/// 内容在各语言 .lproj 的 glossary.json（与 lessons.json 同一套加载方式）。`key` 是稳定的中文键，
/// 代码里 `GlossaryLink(term:)` / `TermChip(term:)` 都用它查；`term` 是当前语言下显示的名字。
struct GlossaryEntry: Identifiable, Codable, Hashable {
    let key: String
    let term: String
    /// market 市场环境 / fundamental 基本面 / structure 结构信号 / general 通用
    let category: String
    /// 大白话解释。
    let plain: String
    /// 举例（可空）。
    let example: String?
    /// 它不代表什么（可空）：防止被读成预测或建议。
    let notMeans: String?

    var id: String { key }
}

enum GlossaryCategory: String, CaseIterable {
    case market, fundamental, structure, general

    var title: String {
        switch self {
        case .market: return L("市场环境")
        case .fundamental: return L("基本面")
        case .structure: return L("结构信号")
        case .general: return L("通用概念")
        }
    }
}

enum GlossaryStore {
    private static var cache: [String: [GlossaryEntry]] = [:]

    static var all: [GlossaryEntry] {
        let lang = Localized.language().rawValue
        if let cached = cache[lang] { return cached }
        let loaded = load()
        cache[lang] = loaded
        return loaded
    }

    static func entry(for key: String) -> GlossaryEntry? {
        all.first { $0.key == key }
    }

    /// 按名字 / 解释搜索（忽略大小写）。
    static func search(_ text: String) -> [GlossaryEntry] {
        let q = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return all }
        return all.filter {
            $0.term.localizedCaseInsensitiveContains(q) || $0.key.localizedCaseInsensitiveContains(q)
                || $0.plain.localizedCaseInsensitiveContains(q)
        }
    }

    private static func load() -> [GlossaryEntry] {
        let bundle = Localized.resourceBundle()
        let url = bundle.url(forResource: "glossary", withExtension: "json")
            ?? Bundle.main.url(forResource: "glossary", withExtension: "json")
        guard let url, let data = try? Data(contentsOf: url),
              let list = try? JSONDecoder().decode([GlossaryEntry].self, from: data) else { return [] }
        return list
    }
}

/// 新手入门词条（guide.json）：和缠论词条同一种结构（LessonArticle），分开存放、分开排序。
enum GuideStore {
    private static var cache: [String: [LessonArticle]] = [:]

    static var all: [LessonArticle] {
        let lang = Localized.language().rawValue
        if let cached = cache[lang] { return cached }
        let bundle = Localized.resourceBundle()
        let url = bundle.url(forResource: "guide", withExtension: "json")
            ?? Bundle.main.url(forResource: "guide", withExtension: "json")
        var list: [LessonArticle] = []
        if let url, let data = try? Data(contentsOf: url) {
            list = (try? JSONDecoder().decode([LessonArticle].self, from: data)) ?? []
        }
        cache[lang] = list
        return list
    }
}
