import Foundation

/// 一篇缠论教程词条。
///
/// 内容存在 Resources/Lessons/lessons.json，不硬编码进 Swift——改文案不必碰代码。
///
/// body 用 Markdown，但只能用**行内**语法（粗体、斜体、行内代码）。SwiftUI 的
/// `AttributedString(markdown:)` 不做块级渲染，`#` 标题和 `-` 列表会原样显示成
/// 字面量。所以段落用空行分隔，项目符号手写 `•`。
struct LessonArticle: Identifiable, Codable, Hashable {
    /// 稳定标识，同时是术语跳转的锚点。改这个值要同步 GlossaryIndex。
    let id: String
    let title: String
    /// 列表页显示的一句话概述。
    let summary: String
    /// Markdown 正文。
    let body: String
}

/// 教程内容的加载与检索。
///
/// 内容是静态的，启动时读一次就够，没必要做成 ObservableObject。
enum LessonStore {
    // 按当前界面语言从对应 .lproj 加载 lessons.json，并按语言缓存。
    // 用户在运行时切换语言后，RootView 靠 .id(language) 重建视图树，会重新读取
    // `all`，从而拿到目标语言的课文（缓存避免重复解析）。
    private static var cache: [String: [LessonArticle]] = [:]

    /// 全部词条，按 JSON 里的顺序（顺序是有意义的：从 K 线处理递进到级别）。
    static var all: [LessonArticle] {
        let lang = Localized.language().rawValue
        if let cached = cache[lang] { return cached }
        let loaded = load()
        cache[lang] = loaded
        return loaded
    }

    static func article(id: String) -> LessonArticle? {
        all.first { $0.id == id }
    }

    /// 读当前语言 .lproj 里的 lessons.json（缺失回退主 Bundle）。
    ///
    /// 失败时返回空数组而不是崩溃：教程加载不了是内容问题，不该让整个 App 起不来。
    /// 学习页会显示加载失败提示，其余功能照常。
    private static func load() -> [LessonArticle] {
        let bundle = Localized.resourceBundle()
        let url = bundle.url(forResource: "lessons", withExtension: "json")
            ?? Bundle.main.url(forResource: "lessons", withExtension: "json")
        guard let url else {
            print("[LessonStore] lessons.json 不在 Bundle 里，检查是否被打进 Copy Bundle Resources")
            return []
        }
        do {
            let data = try Data(contentsOf: url)
            return try JSONDecoder().decode([LessonArticle].self, from: data)
        } catch {
            print("[LessonStore] 解析 lessons.json 失败: \(error)")
            return []
        }
    }
}

/// 术语 → 词条 id 的映射。
///
/// 界面上出现的术语文本和词条标题不总是一致（图例写「顶分型」，词条叫「分型」），
/// 所以要有这张表。查不到时调用方应退化为普通文本，不要出现点不开的死链。
enum GlossaryIndex {
    private static let map: [String: String] = [
        "包含": "inclusion",
        "包含处理": "inclusion",
        "分型": "fractal",
        "顶分型": "fractal",
        "底分型": "fractal",
        "笔": "stroke",
        "线段": "segment",
        "中枢": "pivot",
        "背驰": "divergence",
        // 面积比指向 MACD 词条：那篇才讲了它是怎么算出来的
        "面积比": "macd",
        "MACD": "macd",
        "DIF": "macd",
        "DEA": "macd",
        "买卖点": "trade-points",
        "一买": "trade-points",
        "二买": "trade-points",
        "三买": "trade-points",
        "一卖": "trade-points",
        "二卖": "trade-points",
        "三卖": "trade-points",
        "级别": "level",
        "走势级别": "level",
        // 英文界面下后端返回的买卖点 label 也要能点开对应词条
        "1st Buy": "trade-points",
        "2nd Buy": "trade-points",
        "3rd Buy": "trade-points",
        "1st Sell": "trade-points",
        "2nd Sell": "trade-points",
        "3rd Sell": "trade-points",
    ]

    /// 术语对应的词条，查不到返回 nil。
    static func article(for term: String) -> LessonArticle? {
        guard let id = map[term] else { return nil }
        return LessonStore.article(id: id)
    }

    static func hasEntry(for term: String) -> Bool {
        article(for: term) != nil
    }
}
