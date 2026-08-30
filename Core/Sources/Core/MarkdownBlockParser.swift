import Foundation

/// 行级 markdown 块。inline 标记（**bold**、`code`、链接）保留原样，
/// 由视图层 AttributedString 解析。
public enum MarkdownBlock: Equatable, Sendable {
    case heading(level: Int, text: String)
    case bullet(items: [String])
    case ordered(items: [String])
    case code(String)
    case paragraph(String)
}

public enum MarkdownBlockParser {
    /// 纯行级解析：逐行分类，相邻同类聚合。不做完整 CommonMark——
    /// LLM 输出的标题/列表/代码块/表格覆盖到即可。
    public static func parse(_ markdown: String) -> [MarkdownBlock] {
        var blocks: [MarkdownBlock] = []
        var bullets: [String] = []
        var ordered: [String] = []
        var paragraph: [String] = []
        var codeLines: [String]?
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
        func flushTable() {
            if inTable {
                blocks.append(.code(tableLines.joined(separator: "\n")))
                tableLines = []
                inTable = false
            }
        }
        func flushAll() { flushLists(); flushParagraph(); flushTable() }

        for rawLine in markdown.split(separator: "\n", omittingEmptySubsequences: false) {
            let line = String(rawLine).trimmingCharacters(in: .whitespaces)

            // 围栏代码块：``` 开/闭
            if line.hasPrefix("```") {
                if codeLines == nil {
                    flushAll()
                    codeLines = []
                } else {
                    blocks.append(.code((codeLines ?? []).joined(separator: "\n")))
                    codeLines = nil
                }
                continue
            }
            if codeLines != nil {
                codeLines?.append(String(rawLine))
                continue
            }

            if line.isEmpty { flushAll(); continue }

            // 表格行（| 开头）：连续表格行聚成一个 code 块（等宽对齐降级显示）
            if line.hasPrefix("|") {
                if !inTable { flushAll(); inTable = true }
                tableLines.append(line)
                continue
            } else if inTable {
                flushTable()
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
                flushTable()
                bullets.append(String(m.1))
                continue
            }
            // 有序列表
            if let m = line.firstMatch(of: /^\d+[.)]\s+(.*)$/) {
                flushParagraph()
                flushTable()
                ordered.append(String(m.1))
                continue
            }
            // 普通文本
            flushLists()
            flushTable()
            paragraph.append(line)
        }
        // 收尾
        if let cl = codeLines { blocks.append(.code(cl.joined(separator: "\n"))) }
        flushAll()
        return blocks
    }
}
