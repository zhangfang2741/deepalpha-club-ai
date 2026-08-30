import Foundation

/// 行级 markdown 块。inline 标记（**bold**、`code`、链接）保留原样，
/// 由视图层用 `AttributedString(markdown:)` 解析——那是系统唯一开箱支持的部分。
///
/// 块级（标题/列表/代码/引用/表格）系统不渲染，只能自己分块。这里不用
/// `AttributedString` 的 `presentationIntent` 走 CommonMark：它不支持 GFM 表格，
/// 而 agent 输出财务数据几乎必然带表格，换过去等于把表格降级成一坨纯文本。
public enum MarkdownBlock: Equatable, Sendable {
    case heading(level: Int, text: String)
    case bullet(items: [String])
    case ordered(items: [String])
    /// language 供视图层显示语言角标；未标注时为 nil
    case code(language: String?, text: String)
    case quote(String)
    case table(header: [String], rows: [[String]])
    case paragraph(String)
}

public enum MarkdownBlockParser {
    /// 纯行级解析：逐行分类，相邻同类聚合。不做完整 CommonMark——
    /// LLM 输出的标题/列表/代码块/引用/表格覆盖到即可。
    public static func parse(_ markdown: String) -> [MarkdownBlock] {
        var blocks: [MarkdownBlock] = []
        var bullets: [String] = []
        var ordered: [String] = []
        var paragraph: [String] = []
        var quote: [String] = []
        var codeLines: [String]?
        var codeLanguage: String?
        var tableLines: [String] = []
        var inTable = false

        func flushLists() {
            if !bullets.isEmpty { blocks.append(.bullet(items: bullets)); bullets = [] }
            if !ordered.isEmpty { blocks.append(.ordered(items: ordered)); ordered = [] }
        }
        func flushParagraph() {
            if !paragraph.isEmpty {
                blocks.append(.paragraph(paragraph.joined(separator: "\n")))
                paragraph = []
            }
        }
        func flushQuote() {
            if !quote.isEmpty {
                blocks.append(.quote(quote.joined(separator: "\n")))
                quote = []
            }
        }
        func flushTable() {
            if inTable {
                if let table = Self.makeTable(tableLines) { blocks.append(table) }
                tableLines = []
                inTable = false
            }
        }
        func flushAll() { flushLists(); flushParagraph(); flushQuote(); flushTable() }

        for rawLine in markdown.split(separator: "\n", omittingEmptySubsequences: false) {
            let line = String(rawLine).trimmingCharacters(in: .whitespaces)

            // 围栏代码块：``` 开/闭。开栏行的剩余部分是语言标记
            if line.hasPrefix("```") {
                if codeLines == nil {
                    flushAll()
                    codeLines = []
                    let lang = String(line.dropFirst(3)).trimmingCharacters(in: .whitespaces)
                    codeLanguage = lang.isEmpty ? nil : lang
                } else {
                    blocks.append(.code(language: codeLanguage,
                                        text: (codeLines ?? []).joined(separator: "\n")))
                    codeLines = nil
                    codeLanguage = nil
                }
                continue
            }
            if codeLines != nil {
                codeLines?.append(String(rawLine))
                continue
            }

            if line.isEmpty { flushAll(); continue }

            // 表格行（| 开头）：连续表格行聚成一个 table
            if line.hasPrefix("|") {
                if !inTable { flushLists(); flushParagraph(); flushQuote(); inTable = true }
                tableLines.append(line)
                continue
            } else if inTable {
                flushTable()
            }

            // 引用块：> 后的空格可有可无
            if let m = line.firstMatch(of: /^>\s?(.*)$/) {
                flushLists()
                flushParagraph()
                quote.append(String(m.1))
                continue
            } else if !quote.isEmpty {
                flushQuote()
            }

            // 标题（1-6 级）
            if let m = line.firstMatch(of: /^(#{1,6})\s+(.*)$/) {
                flushAll()
                blocks.append(.heading(level: m.1.count, text: String(m.2)))
                continue
            }
            // 无序列表
            if let m = line.firstMatch(of: /^[-*+]\s+(.*)$/) {
                flushParagraph()
                bullets.append(String(m.1))
                continue
            }
            // 有序列表
            if let m = line.firstMatch(of: /^\d+[.)]\s+(.*)$/) {
                flushParagraph()
                ordered.append(String(m.1))
                continue
            }
            // 普通文本
            flushLists()
            paragraph.append(line)
        }
        // 收尾
        if let cl = codeLines {
            blocks.append(.code(language: codeLanguage, text: cl.joined(separator: "\n")))
        }
        flushAll()
        return blocks
    }

    /// 把 `| a | b |` 形式的行拼成表格。首行当表头，`|---|---|` 分隔行丢弃，
    /// 缺列补空串——LLM 输出的表格列数不齐是常态，不能因此丢整张表。
    private static func makeTable(_ lines: [String]) -> MarkdownBlock? {
        let rows = lines.compactMap { line -> [String]? in
            let cells = splitRow(line)
            // 分隔行（只有 -、: 和空格）不是数据
            let isSeparator = cells.allSatisfy { cell in
                !cell.isEmpty && cell.allSatisfy { $0 == "-" || $0 == ":" || $0 == " " }
            }
            return (cells.isEmpty || isSeparator) ? nil : cells
        }
        guard let header = rows.first else { return nil }
        let width = header.count
        let body = rows.dropFirst().map { row -> [String] in
            row.count >= width
                ? Array(row.prefix(width))
                : row + Array(repeating: "", count: width - row.count)
        }
        return .table(header: header, rows: Array(body))
    }

    /// 拆一行单元格：去掉首尾竖线后按 | 切分。
    private static func splitRow(_ line: String) -> [String] {
        var trimmed = Substring(line)
        if trimmed.hasPrefix("|") { trimmed = trimmed.dropFirst() }
        if trimmed.hasSuffix("|") { trimmed = trimmed.dropLast() }
        return trimmed
            .split(separator: "|", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespaces) }
    }
}
