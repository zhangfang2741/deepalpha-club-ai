import SwiftUI
import DeepAlphaCore

/// 轻量 markdown 渲染。
///
/// 分工：块级（标题/列表/代码/引用/表格）由 Core 的 MarkdownBlockParser 切好，
/// 这里逐块渲染；行内（**粗体**、*斜体*、`code`、[链接]）交给系统的
/// `AttributedString(markdown:)` ——那是 Apple 唯一开箱支持 markdown 的地方。
///
/// 行内 code 需要额外处理：系统只标出 `.code` 这个 inlinePresentationIntent，
/// 不给任何视觉样式，得自己按 run 补上等宽字体和底色。
struct MarkdownText: View {
    let markdown: String
    /// 正文字号。推理流用 footnote，回放页可放大。
    var font: Font = .footnote

    private var blocks: [MarkdownBlock] { MarkdownBlockParser.parse(markdown) }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                blockView(block)
            }
        }
        .font(font)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func blockView(_ block: MarkdownBlock) -> some View {
        switch block {
        case .heading(let level, let text):
            headingView(level: level, text: text)
        case .paragraph(let text):
            Text(inline(text))
                .foregroundStyle(Theme.textPrimary)
                .frame(maxWidth: .infinity, alignment: .leading)
        case .bullet(let items):
            listView(items) { _ in
                Text("•")
                    .foregroundStyle(Theme.accent)
                    .frame(width: 14, alignment: .leading)
            }
        case .ordered(let items):
            listView(items) { i in
                Text("\(i + 1).")
                    .monospacedDigit()
                    .foregroundStyle(Theme.accent)
                    .frame(width: 20, alignment: .leading)
            }
        case .code(let language, let text):
            codeBlock(language: language, text: text)
        case .quote(let text):
            quoteBlock(text)
        case .table(let header, let rows):
            tableBlock(header: header, rows: rows)
        }
    }

    // MARK: - 各块

    /// 标题：一二级明显大一号并加粗，三级往下退回正文字号但仍加粗，
    /// 层级差异要能一眼看出来，否则 ## 和 ### 混成一片。
    private func headingView(level: Int, text: String) -> some View {
        Text(inline(text))
            .font(level <= 1 ? .title3.bold()
                  : level == 2 ? .headline
                  : .subheadline.weight(.semibold))
            .foregroundStyle(Theme.textPrimary)
            .padding(.top, level <= 2 ? 4 : 2)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func listView(
        _ items: [String],
        @ViewBuilder marker: @escaping (Int) -> some View
    ) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            ForEach(Array(items.enumerated()), id: \.offset) { i, item in
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    marker(i)
                    Text(inline(item))
                        .foregroundStyle(Theme.textPrimary)
                    Spacer(minLength: 0)
                }
            }
        }
    }

    /// 代码块：带语言角标，横向可滚。滚动条常驻提示——不显示的话用户
    /// 根本不知道右边还有内容，只会看到一句被切断的代码。
    private func codeBlock(language: String?, text: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            if let language, !language.isEmpty {
                Text(language.uppercased())
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .tracking(0.8)
                    .foregroundStyle(Theme.textTertiary)
                    .padding(.horizontal, 10)
                    .padding(.top, 8)
            }
            ScrollView(.horizontal) {
                Text(text)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(Theme.textPrimary)
                    .textSelection(.enabled)
                    .padding(10)
            }
            // 右缘渐隐：代码在窄屏必然被切断，不给暗示的话用户只会看到
            // 一句断掉的代码，不会想到能横滑。内容没超宽时这层与底色同色，看不出来。
            .overlay(alignment: .trailing) {
                LinearGradient(
                    colors: [Theme.surfaceAlt.opacity(0), Theme.surfaceAlt],
                    startPoint: .leading, endPoint: .trailing)
                    .frame(width: 24)
                    .allowsHitTesting(false)
            }
        }
        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .strokeBorder(Theme.border, lineWidth: 1))
    }

    /// 引用块：左竖线 + 次级字色，与正文拉开层次。
    private func quoteBlock(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            RoundedRectangle(cornerRadius: 1.5)
                .fill(Theme.accent.opacity(0.6))
                .frame(width: 3)
            Text(inline(text))
                .foregroundStyle(Theme.textSecondary)
                .italic()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .fixedSize(horizontal: false, vertical: true)
        .padding(.vertical, 2)
    }

    /// 表格：Grid 逐格渲染。列多时整体横滑，不挤压文字。
    private func tableBlock(header: [String], rows: [[String]]) -> some View {
        ScrollView(.horizontal) {
            Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 6) {
                GridRow {
                    ForEach(Array(header.enumerated()), id: \.offset) { _, cell in
                        Text(inline(cell))
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Theme.textPrimary)
                    }
                }
                Divider().gridCellUnsizedAxes(.horizontal).background(Theme.border)
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    GridRow {
                        ForEach(Array(row.enumerated()), id: \.offset) { _, cell in
                            Text(inline(cell))
                                .font(.caption)
                                .foregroundStyle(Theme.textPrimary)
                        }
                    }
                }
            }
            .padding(10)
        }
        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - 行内

    /// 行内 markdown 交给系统解析，再补上系统不给的 code 样式。
    private func inline(_ s: String) -> AttributedString {
        var attributed = (try? AttributedString(
            markdown: s,
            options: .init(
                allowsExtendedAttributes: true,
                interpretedSyntax: .inlineOnlyPreservingWhitespace,
                failurePolicy: .returnPartiallyParsedIfPossible)))
            ?? AttributedString(s)

        // 粗体/斜体/删除线 SwiftUI 会自己渲染；`code` 只标 intent 不给样式
        for run in attributed.runs where
            run.inlinePresentationIntent?.contains(.code) == true {
            attributed[run.range].font = .system(.caption, design: .monospaced)
            attributed[run.range].foregroundColor = Theme.accent
        }
        return attributed
    }
}
