import SwiftUI

/// 词条详情。既作为学习页的下钻目标，也作为术语点击后弹出的 sheet。
struct LessonDetailView: View {
    let article: LessonArticle
    /// 以 sheet 形式弹出时显示关闭按钮；从列表 push 进来时不需要。
    var showsCloseButton = false

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        content
            .background(Theme.background)
            .navigationTitle(article.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if showsCloseButton {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button(L("完成")) { dismiss() }
                    }
                }
            }
    }

    private var content: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text(article.summary)
                    .font(.subheadline)
                    .foregroundColor(Theme.textSecondary)
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                // 示意图放在摘要之后、正文之前：先看图建立直观印象，再读定义。
                if let spec = LessonDiagrams.spec(for: article.id) {
                    VStack(alignment: .leading, spacing: 6) {
                        LessonDiagram(spec: spec)
                        Text(L("示意图，与分析页使用同一套配色"))
                            .font(.caption2)
                            .foregroundColor(Theme.textSecondary)
                    }
                }

                // 按空行切段落分别渲染，而不是把整篇丢给一个 Text：
                // AttributedString 的 Markdown 解析默认会把换行折叠掉，
                // 整篇渲染出来会是没有段落的一大坨。
                ForEach(Array(paragraphs.enumerated()), id: \.offset) { _, paragraph in
                    Text(markdown(paragraph))
                        .font(.system(size: 15))
                        .foregroundColor(Theme.textPrimary)
                        .lineSpacing(6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                }

                Text(L("以上为缠论的通行解读，仅供学习参考，不构成投资建议。"))
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
                    .padding(.top, 8)
            }
            // 这一页正文是裸 Text（没有卡片背景兜底），水平边距不跟着列表页收窄，
            // 否则文字会直接贴到屏幕边上。
            .padding(18)
        }
    }

    private var paragraphs: [String] {
        article.body
            .components(separatedBy: "\n\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    /// 解析行内 Markdown。解析失败就退回纯文本，不能因为一个星号没配对就丢内容。
    private func markdown(_ text: String) -> AttributedString {
        // .inlineOnlyPreservingWhitespace 保留段落内的单换行（项目符号列表靠它分行）
        (try? AttributedString(
            markdown: text,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        )) ?? AttributedString(text)
    }
}
